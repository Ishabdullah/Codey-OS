"""Individual CCOS entry points for extended Termux:API commands."""
from ccos.plugins.device.termux_api import extended_api as e

audio_info = e.audio_info
call_log = e.call_log
fingerprint = e.fingerprint
infrared_frequencies = e.infrared_frequencies
keystore = e.keystore
media_player = e.media_player
media_scan = e.media_scan
nfc = e.nfc
toast = e.toast
saf_dirs = e.saf_dirs
saf_managedir = e.saf_managedir
saf_ls = e.saf_ls
saf_mkdir = e.saf_mkdir
saf_create = e.saf_create
saf_read = e.saf_read
saf_write = e.saf_write
saf_rm = e.saf_rm
saf_stat = e.saf_stat
notification_channel = e.notification_channel
