#!/bin/bash
#
# FlexROV - turn the Raspberry Pi into a WiFi access point.
#
# After this runs you never touch the control PC's network settings again:
#   1. Join WiFi network "hotspot" with password "11111111"
#   2. Open http://192.168.4.1  (or: ssh <user>@192.168.4.1)
#
# Built on hostapd + dnsmasq so it works on every Linux distro and version,
# not just Raspberry Pi OS. No internet is shared or needed - the ROV is
# standalone, which also means clients need no DNS.
#
# Run once:  sudo ./setup_hotspot.sh
# Undo:      sudo ./stop_hotspot.sh

# ---------------------------------------------------------------- settings ----
SSID="hotspot"
# WPA2-PSK only accepts 8..63 characters, so "1111" cannot be used as-is.
PSK="11111111"
AP_IP="192.168.4.1"
DHCP_FIRST="192.168.4.2"
DHCP_LAST="192.168.4.50"
CHANNEL="6"
BAND="g"              # g = 2.4GHz (works on every Pi). a = 5GHz if you prefer.
COUNTRY_CODE="US"     # change to your ISO code, e.g. GB, DE, PL
# ---------------------------------------------------------------------------

set -euo pipefail

HOSTAPD_CONF="/etc/hostapd/hostapd-flexrov.conf"
DNSMASQ_DIR="/etc/dnsmasq.d"
DNSMASQ_CONF="$DNSMASQ_DIR/flexrov.conf"
START_CMD="/usr/local/sbin/flexrov-hotspot-start"
STOP_CMD="/usr/local/sbin/flexrov-hotspot-stop"
UNIT="/etc/systemd/system/flexrov-hotspot.service"
INITD="/etc/init.d/flexrov-hotspot"
NETD_NETWORK="/etc/systemd/network/10-flexrov-ap.network"

info() { printf '\033[36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m  ok\033[0m %s\n' "$*"; }
warn() { printf '\033[33m  !!\033[0m %s\n' "$*"; }
die()  { printf '\033[31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || { command -v sudo >/dev/null || die "run as root"; exec sudo -E bash "$0" "$@"; }

case "${#PSK}" in
  ''|???????) die "PSK must be 8..63 characters (got ${#PSK}). Edit PSK near the top of setup_hotspot.sh." ;;
esac

# --------------------------------------------------------- helper routines ----
detect_wlan() {
    local path name
    for path in /sys/class/net/*/wireless; do
        [ -e "$path" ] || continue
        name=${path%/wireless}
        echo "${name##*/}"
        return 0
    done
    return 1
}

ensure_pkgs() {
    local need="" p
    for p in "$@"; do
        command -v "$p" >/dev/null 2>&1 || need="$need $p"
    done
    if [ -z "${need# }" ]; then
        return 0
    fi
    info "Installing hostapd / dnsmasq"
    # shellcheck disable=SC2086
    set -- $need
    if command -v apt-get >/dev/null; then
        DEBIAN_FRONTEND=noninteractive apt-get update -qq
        DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"
    elif command -v dnf >/dev/null; then dnf install -y "$@"
    elif command -v yum >/dev/null; then yum install -y "$@"
    elif command -v zypper >/dev/null; then zypper --non-interactive install "$@"
    elif command -v pacman >/dev/null; then pacman -Sy --noconfirm "$@"
    elif command -v apk >/dev/null; then apk add --no-cache "$@"
    else die "no supported package manager; install hostapd and dnsmasq manually"
    fi
}

# Hand the radio to hostapd: every network manager that wants to *connect*
# on this interface will happily undo AP mode behind our back.
free_interface() {
    local iface="$1"

    if command -v nmcli >/dev/null 2>&1 && systemctl is-active --quiet NetworkManager 2>/dev/null; then
        info "NetworkManager: marking $iface as unmanaged"
        nmcli device set "$iface" managed no >/dev/null 2>&1 || true
    fi

    if systemctl is-active --quiet iwd 2>/dev/null; then
        info "Stopping iwd (it cannot share the radio with an AP)"
        systemctl stop iwd >/dev/null 2>&1 || true
        systemctl disable iwd >/dev/null 2>&1 || true
    fi

    if systemctl is-enabled --quiet systemd-networkd 2>/dev/null; then
        info "systemd-networkd: pinning $iface to $AP_IP"
        mkdir -p "$(dirname "$NETD_NETWORK")"
        cat > "$NETD_NETWORK" <<EOF
# FlexROV hotspot
[Match]
Name=$iface

[Network]
DHCP=no
Address=$AP_IP/24
EOF
        systemctl reload systemd-networkd >/dev/null 2>&1 || true
    fi

    # Raspberry Pi OS: dhcpcd + wpa_supplicant run a client-mode scan loop.
    if [ -f /etc/dhcpcd.conf ] && ! grep -qs "denyinterfaces $iface" /etc/dhcpcd.conf; then
        printf '\n# FlexROV hotspot\ndenyinterfaces %s\n' "$iface" >> /etc/dhcpcd.conf
        ok "dhcpcd.conf: added denyinterfaces $iface"
    fi

    if [ -f /etc/wpa_supplicant/wpa_supplicant.conf ]; then
        if grep -qsE '^[[:space:]]*network[[:space:]]*=' /etc/wpa_supplicant/wpa_supplicant.conf; then
            warn "wpa_supplicant has saved networks - stopping it so it cannot retake $iface"
            systemctl stop wpa_supplicant >/dev/null 2>&1 || true
            systemctl disable wpa_supplicant >/dev/null 2>&1 || true
        else
            ok "wpa_supplicant.conf: client mode disabled"
            cat > /etc/wpa_supplicant/wpa_supplicant.conf <<EOF
# Rewritten by FlexROV setup_hotspot.sh - no saved networks, client mode off.
# $iface runs as an access point via hostapd.
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country_code=$COUNTRY_CODE
EOF
        fi
    fi

    # The distro's own hostapd must not also try to own the radio.
    systemctl stop hostapd.service >/dev/null 2>&1 || true
    systemctl mask hostapd.service >/dev/null 2>&1 || true
}

write_configs() {
    local iface="$1"

    mkdir -p /etc/hostapd "$DNSMASQ_DIR"
    cat > /etc/hostapd/hostapd.conf <<EOF
DAEMON_CONF=$HOSTAPD_CONF
EOF
    cat > "$HOSTAPD_CONF" <<EOF
# FlexROV hotspot
interface=$iface
driver=nl80211
ssid=$SSID
country_code=$COUNTRY_CODE

hw_mode=$BAND
channel=$CHANNEL
ieee80211n=1
wmm_enabled=1
beacon_int=100

auth_algs=1
wpa=2
wpa_passphrase=$PSK
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
wpa_pairwise=CCMP
wpa_group_rekey=3600
wpa_ptk_rekey=600
EOF
    chmod 600 "$HOSTAPD_CONF"
    cat > "$DNSMASQ_CONF" <<EOF
# FlexROV hotspot - DHCP for $iface only.
# DNS is switched off at run time (-p 0): the ROV has no internet, so there is
# nothing to resolve, and it avoids clashing with a distro dnsmasq on port 53.
interface=$iface
bind-dynamic
dhcp-authoritative
dhcp-range=$DHCP_FIRST,$DHCP_LAST,255.255.255.0,12h
dhcp-option=3,$AP_IP
dhcp-option=42,$AP_IP
EOF
    ok "wrote $HOSTAPD_CONF"
    ok "wrote $DNSMASQ_CONF"
}

write_service_scripts() {
    local iface="$1"

    cat > "$START_CMD" <<EOF
#!/bin/bash
# Brings up the FlexROV hotspot. Generated by setup_hotspot.sh - do not edit.
set -e
IFACE="$iface"

ip link set "\$IFACE" up
ip addr flush dev "\$IFACE"
ip addr add $AP_IP/24 dev "\$IFACE"

dnsmasq --conf-file=$DNSMASQ_CONF --pid-file=/run/dnsmasq-flexrov.pid -p 0
hostapd -B -P /run/hostapd-flexrov.pid $HOSTAPD_CONF
EOF

    cat > "$STOP_CMD" <<EOF
#!/bin/bash
# Tears the FlexROV hotspot down. Generated by setup_hotspot.sh - do not edit.
IFACE="$iface"
[ -f /run/hostapd-flexrov.pid ]  && kill "\$(cat /run/hostapd-flexrov.pid)"  2>/dev/null
[ -f /run/dnsmasq-flexrov.pid ]  && kill "\$(cat /run/dnsmasq-flexrov.pid)"  2>/dev/null
sleep 1
ip addr flush dev "\$IFACE" 2>/dev/null
rm -f /run/hostapd-flexrov.pid /run/dnsmasq-flexrov.pid
exit 0
EOF

    chmod 755 "$START_CMD" "$STOP_CMD"
    ok "wrote $START_CMD and $STOP_CMD"
}

register_service() {
    local iface="$1"

    if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
        cat > "$UNIT" <<EOF
# FlexROV hotspot - WiFi AP on $iface at $AP_IP
[Unit]
Description=FlexROV control hotspot
After=network-pre.target
Wants=network-pre.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=$START_CMD
ExecStop=$STOP_CMD

[Install]
WantedBy=multi-user.target
EOF
        systemctl daemon-reload
        systemctl enable flexrov-hotspot.service >/dev/null 2>&1
        ok "registered systemd service flexrov-hotspot.service"
        systemctl restart flexrov-hotspot.service \
            || warn "flexrov-hotspot.service failed to start - check: journalctl -u flexrov-hotspot"
    elif command -v rc-update >/dev/null 2>&1; then
        cat > "$INITD" <<EOF
#!/sbin/openrc-run
# FlexROV hotspot
depend() { need net; after bootmisc; }
start() { ebegin "FlexROV hotspot"; $START_CMD; eend \$?; }
stop()  { ebegin "FlexROV hotspot"; $STOP_CMD; eend \$?; }
EOF
        chmod 755 "$INITD"
        rc-update add flexrov-hotspot default >/dev/null 2>&1
        ok "registered OpenRC service flexrov-hotspot"
        rc-service flexrov-hotspot restart || warn "flexrov-hotspot failed to start"
    elif [ -d /etc/init.d ]; then
        cat > "$INITD" <<EOF
#!/bin/sh
### BEGIN INIT INFO
# Provides:          flexrov-hotspot
# Required-Start:    \$network
# Required-Stop:     \$network
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: FlexROV control hotspot
### END INIT INFO
# FlexROV hotspot
case "\$1" in
  start)   echo "Starting FlexROV hotspot"; $START_CMD ;;
  stop)    echo "Stopping FlexROV hotspot"; $STOP_CMD ;;
  restart) "\$0" stop; sleep 1; "\$0" start ;;
  *)       echo "Usage: \$0 {start|stop|restart}"; exit 1 ;;
esac
EOF
        chmod 755 "$INITD"
        command -v chkconfig >/dev/null 2>&1 && chkconfig --add flexrov-hotspot 2>/dev/null || true
        command -v update-rc.d >/dev/null 2>&1 && update-rc.d flexrov-hotspot defaults 2>/dev/null || true
        ok "registered SysV init script flexrov-hotspot"
        "$INITD" restart || warn "flexrov-hotspot failed to start"
    else
        warn "no service manager found - starting the hotspot now, it will NOT survive a reboot"
        "$START_CMD"
    fi
}

verify() {
    local iface="$1"
    sleep 3
    if ip -4 addr show dev "$iface" 2>/dev/null | grep -q "$AP_IP"; then
        ok "$iface has $AP_IP"
    else
        die "$iface did not get $AP_IP - run 'sudo ./stop_hotspot.sh' then check 'ip link' for the wifi adapter"
    fi
    if pgrep -x hostapd >/dev/null 2>&1; then
        ok "hostapd is broadcasting"
    else
        warn "hostapd is not running - try: hostapd -d $HOSTAPD_CONF"
    fi
}

# ------------------------------------------------------------------- main ----
iface=$(detect_wlan) || die "no wireless interface found (expected /sys/class/net/wlan*/wireless)"
info "Wireless interface: $iface"

ensure_pkgs hostapd dnsmasq
free_interface "$iface"
write_configs "$iface"
write_service_scripts "$iface"
register_service "$iface"
verify "$iface"

cat <<EOF

$(printf '\033[32m%s\033[0m' 'FlexROV hotspot is up.')
--------------------------------------------------------------
  WiFi network (SSID):  $SSID
  Password:             $PSK
  Pi address:           $AP_IP

  On the control PC: join the WiFi network above, then open

      http://$AP_IP

  or

      ssh <your-user>@$AP_IP
--------------------------------------------------------------
  The hotspot starts automatically on every boot.
  Undo with:  sudo ./stop_hotspot.sh
EOF
