from dataclasses import asdict
import json
import os
from pathlib import Path
import re

from yall_run.model import load_spec

root = Path('examples/yall')
paths = [p for p in sorted(root.rglob('Yallfile*'))
         if p.is_file() and len(p.read_text().splitlines()) > 40
         and re.search(r'^campaign ', p.read_text(), re.M)]
assert paths, 'No complex Yallfile examples found'
comment = "# Set to full to record operator accounts when permitted by your site's privacy policy.\n%account-provenance off\n"
summary = []
for path in paths:
    original = path.read_text()
    assert '%account-provenance' not in original, str(path)
    for name in re.findall(r'^@env\s+([A-Za-z_][A-Za-z0-9_]*)\s*$', original, re.M):
        os.environ.setdefault(name, '/tmp/lfhcal-privacy-validation/' + name)
    before = load_spec(path)
    changed, count = re.subn(r'(^backend [^\n]+\n)', lambda m: m[1] + '\n' + comment,
                             original, count=1, flags=re.M)
    if not count:
        changed, count = re.subn(r'(^campaign [^\n]+\n)', lambda m: m[1] + '\n' + comment,
                                 original, count=1, flags=re.M)
    assert count == 1, str(path)
    path.write_text(changed)
    after = load_spec(path)
    assert after.account_provenance == 'off'
    assert asdict(before) == asdict(after), 'Expanded workflow changed: ' + str(path)
    summary.append({'file': str(path), 'tasks': len(after.tasks), 'backend': after.backend,
                    'expanded_workflow_unchanged': True})

readme = root / 'README.md'
readme.write_text(readme.read_text().rstrip() + '''

## Account provenance

The larger examples explicitly set `%account-provenance off`, with a comment
showing when to select `full`. This directive requires **yall-run 0.12.0a7 or
newer**. Account recording also defaults to off when the directive is omitted.

Use `full` to preserve creator, submitter, and host-worker account attribution
when permitted by your site's privacy policy. A creation-time
`--account-provenance full` or `--account-provenance off` overrides the recipe;
the resolved choice is frozen for that campaign before any account lookup.

This controls explicit OS-account snapshots only. Paths, command arguments,
logs, scheduler records, and analysis outputs are not anonymized. Existing
campaigns and their archived workers are not retroactively changed.
''')
print(json.dumps({'validated_examples': len(summary), 'examples': summary}, indent=2))
