"""Interactive macOS Keychain storage; secrets are never command arguments."""
import getpass,json,sys
import keyring
if sys.platform!='darwin':raise SystemExit('Use the Windows DPAPI scripts on Windows.')
keyring.set_password('instagram-auto-post','instagram-token',getpass.getpass('Instagram token: '))
value={name:getpass.getpass(name+': ') for name in ('cloud_name','api_key','api_secret')}
keyring.set_password('instagram-auto-post','cloudinary',json.dumps(value))
print('Saved in system keychain.')
