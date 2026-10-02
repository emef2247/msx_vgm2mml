"""Copy batch MGS outputs into one directory per title for MSX playback."""
import argparse
import filecmp
from pathlib import Path
import shutil


def collect_mgs(source, output, *, dry_run=False, overwrite=False):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_dir():
        raise ValueError(f'Input directory not found: {source}')
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('Input and output directory trees must be separate')
    files = sorted(p for p in source.rglob('*') if p.is_file() and p.suffix.lower() == '.mgs')
    if not files:
        raise ValueError(f'No MGS files found: {source}')
    plan, targets = [], {}
    for path in files:
        # Batch output is <title>/<track>.vgm/<track>.mgs (also .vgz).
        title = path.parent.parent.name if path.parent.suffix.lower() in ('.vgm', '.vgz') else path.parent.name
        target = output / title / path.name
        if output not in target.resolve().parents:
            raise ValueError(f'Copy destination escapes output directory: {target}')
        key = (title.casefold(), path.name.casefold())
        if key in targets:
            raise ValueError(f'Duplicate destination {target}:\n  {targets[key]}\n  {path}')
        targets[key] = path
        skip = False
        if target.exists():
            if not target.is_file():
                raise ValueError(f'Destination is not a file: {target}')
            skip = filecmp.cmp(path, target, shallow=False)
            if not skip and not overwrite:
                raise ValueError(f'Different file already exists: {target}; use --overwrite to replace it')
        plan.append((path, target, skip))
    # Validate every collision before copying the first file.
    copied, skipped = 0, 0
    for path, target, skip in plan:
        if skip:
            skipped += 1
            continue
        print(f'{path.relative_to(source)} -> {target.relative_to(output)}')
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            if overwrite:
                shutil.copy2(path, target)
            else:
                with path.open('rb') as reader, target.open('xb') as writer:
                    shutil.copyfileobj(reader, writer)
                shutil.copystat(path, target)
        copied += 1
    print(f'{"Would copy" if dry_run else "Copied"}: {copied}; unchanged: {skipped}; titles: {len({p.parent.name for _, p, _ in plan})}')
    return copied, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_dir', type=Path, help='Batch output tree to scan recursively')
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true', help='Preview paths without creating files')
    parser.add_argument('--overwrite', action='store_true', help='Replace different existing destination files')
    args = parser.parse_args()
    try:
        collect_mgs(args.input_dir, args.outdir, dry_run=args.dry_run, overwrite=args.overwrite)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
