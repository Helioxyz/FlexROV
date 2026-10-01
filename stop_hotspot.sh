#!/bin/bash
#
# FlexROV - undo setup_hotspot.sh. Removes the access point and gives the
# wireless adapter back to whatever network manager the distro uses.
#
# Run:  sudo ./stop_hotspot.sh

set -euo pipefail

HOSTAPD_CONF="/etc/hostapd/hostapd-flexrov.conf"
DNSMASQ_CONF="/etc/dnsmasq.d/flexrov.conf"
START_CMD="/usr/local/sbin/flexrov-hotspot-start"
STOP_CMD="/usr/local/sbin/flexrov-hotspot-stop"
UNIT="/etc/systemd/system/flexrov-hotspot.service"
INITD="/etc/init.d/flexrov-hotspot"
NETD_NETWORK="/etc/systemd/network/10-flexrov-ap.network"

info() { printf '\033[36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m  ok\033[0m %s\n' "$*"; }
warn() { printf '\033[33m  !!\033[0m %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { command -v sudo >/dev/null || { echo "ERROR: run as root" >&2; exit 1; }; exec sudo -E bash "$0" "$@"; }

# ---------------------------------------------------------------- stop it ----
if [ -x "$STOP_CMD" ]; then
    "$STOP_CMD" && ok "hotspot processes stopped"
else
    warn "$STOP_CMD missing - killing hostapd/dnsmasq by hand"
    pkill -x hostapd 2>/dev/null || true
    [ -f /run/dnsmasq-flexrov.pid ] && kill "$(cat /run/dnsmasq-flexrov.pid)" 2>/dev/null || true
fi

# ------------------------------------------------------------ deregister -----
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    systemctl disable --now flexrov-hotspot.service >/dev/null 2>&1 || true
    rm -f "$UNIT"
    systemctl unmask hostapd.service >/dev/null 2>&1 || true
    systemctl daemon-reload
    ok "removed systemd service"
    if [ -f "$NETD_NETWORK" ]; then
        rm -f "$NETD_NETWORK"
        systemctl reload systemd-networkd >/dev/null 2>&1 || true
        ok "removed systemd-networkd config"
    fi
elif command -v rc-update >/dev/null 2>&1; then
    rc-service flexrov-hotspot stop >/dev/null 2>&1 || true
    rc-update del flexrov-hotspot default >/dev/null 2>&1 || true
    rm -f "$INITD"
    ok "removed OpenRC service"
elif [ -f "$INITD" ]; then
    "$INITD" stop >/dev/null 2>&1 || true
    command -v update-rc.d >/dev/null 2>&1 && update-rc.d -f flexrov-hotspot remove >/dev/null 2>&1 || true
    command -v chkconfig >/dev/null 2>&1 && chkconfig --del flexrov-hotspot >/dev/null 2>&1 || true
    rm -f "$INITD"
    ok "removed SysV init script"
fi

# --------------------------------------------------------- hand it back -----
rm -f "$START_CMD" "$STOP_CMD" "$HOSTAPD_CONF" "$DNSMASQ_CONF"
ok "removed hotspot configs"

if [ -f /etc/dhcpcd.conf ]; then
    sed -i '/^[[:space:]]*# FlexROV hotspot$/d; /^[[:space:]]*denyinterfaces[[:space:]]*wlan/d' /etc/dhcpcd.conf
    ok "reverted /etc/dhcpcd.conf"
fi

if command -v nmcli >/dev/null 2>&1 && systemctl is-active --quiet NetworkManager 2>/dev/null; then
    for iface in /sys/class/net/wlan*; do
        [ -e "$iface" ] || continue
        name=${iface##*/}
        nmcli device set "$name" managed yes >/dev/null 2>&1 || true
        ok "NetworkManager manages $name again"
    done
fi

printf '\n\033[32mFlexROV hotspot removed.\033[0m\n'
