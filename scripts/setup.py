"""Create local configuration without overwriting user settings."""
from pathlib import Path
import shutil
root=Path(__file__).resolve().parents[1]
for source in (root/'config').glob('*.example.json'):
    target=source.with_name(source.name.replace('.example',''))
    if not target.exists():shutil.copyfile(source,target)
(root/'data/inbox').mkdir(parents=True,exist_ok=True)
print('Local configuration ready. Edit config/publishing.json for your account.')
