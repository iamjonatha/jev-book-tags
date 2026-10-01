#!/bin/zsh
DEMO_DIR="${0:A:h}"
# calibre forwards launches to an existing instance, retaining its profile/language.
if /usr/bin/pgrep -x calibre >/dev/null || /usr/bin/pgrep -f "/Applications/calibre.app/Contents/MacOS/calibre-debug.* -g" >/dev/null; then
    print 'Please quit calibre completely (Cmd+Q), then run this demo launcher again.'
    print 'The running instance has been left unchanged.'
    read -r '?Press Enter to close this window.'
    exit 1
fi
export CALIBRE_CONFIG_DIRECTORY="$DEMO_DIR/calibre-config"
export CALIBRE_OVERRIDE_LANG=en
# The CLI runtime preserves the isolated profile on macOS.
exec /Applications/calibre.app/Contents/MacOS/calibre-debug --run-without-debug -g -- --with-library "$DEMO_DIR/calibre-library" --no-update-check
