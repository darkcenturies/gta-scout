"""Measure explicit placement/material contracts; never infer semantic uprightness."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np


def array(value, shape, name):
    result = np.asarray(value, dtype=float)
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError(f'{name}: expected finite {shape} array')
    return result


def audit(data):
    if data.get('schema') != 1:
        raise ValueError('Expected schema 1')
    findings = []
    for row in data.get('placements', []):
        name = row['id']
        matrix = array(row['world_matrix'], (4, 4), name)
        if not np.allclose(matrix[3], [0, 0, 0, 1]):
            raise ValueError(f'{name}: expected affine matrix')
        up = array(row['local_up'], (3,), name)
        reference = array(row['expected_world_up'], (3,), name)
        actual = matrix[:3, :3] @ up
        if min(np.linalg.norm(actual), np.linalg.norm(reference)) < 1e-8:
            raise ValueError(f'{name}: zero up vector')
        dot = float(np.dot(actual, reference) / (np.linalg.norm(actual) * np.linalg.norm(reference)))
        determinant = float(np.linalg.det(matrix[:3, :3]))
        if abs(determinant) < 1e-8:
            raise ValueError(f'{name}: singular placement')
        findings.append(dict(id=name, check='orientation', passed=dot >= .99 and determinant > 0,
                             up_dot=dot, determinant=determinant, evidence=row['evidence']))
        # The producer samples the actual support surface, not a global Z=0 plane.
        for contact in row.get('contacts', []):
            anchor = matrix @ np.append(array(contact['local_point'], (3,), name), 1)
            support = array(contact['support_world'], (3,), name)
            normal = array(contact['support_normal'], (3,), name)
            if np.linalg.norm(normal) < 1e-8:
                raise ValueError(f'{name}: zero support normal')
            gap = float(np.dot(anchor[:3] - support, normal / np.linalg.norm(normal)))
            lo, hi = array(contact['gap_range'], (2,), name)
            if lo > hi:
                raise ValueError(f'{name}: reversed gap range')
            findings.append(dict(id=name, check='support', passed=bool(lo <= gap <= hi), gap=gap))
    for row in data.get('surfaces', []):
        baseline, candidate = row['baseline'], row['candidate']
        for field in ('texture_sha256', 'geometry_surface', 'material_surface'):
            if field.endswith('_surface'):
                equal = bool(np.allclose(array(baseline[field], (3,), field),
                                         array(candidate[field], (3,), field), rtol=0, atol=1e-6))
            else:
                for entry in (baseline, candidate):
                    digest = entry[field]
                    if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                        raise ValueError('Expected lowercase SHA-256')
                equal = baseline[field] == candidate[field]
            findings.append(dict(id=row['id'], check=field, passed=equal,
                                 baseline=baseline[field], candidate=candidate[field]))
        # Names identify a dictionary binding; pixel identity is checked separately.
        if not baseline.get('texture_identity') or not candidate.get('texture_identity'):
            raise ValueError('Supply source/dictionary/name texture identities')
    return dict(schema=1, passed=bool(findings) and all(x['passed'] for x in findings),
                findings=findings, visual_acceptance=False, runtime_acceptance=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error('Output must not overwrite input')
    raw = args.input.read_bytes()
    result = audit(json.loads(raw))
    result['input_sha256'] = hashlib.sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f"{len(result['findings'])} measurements; passed={result['passed']}; visuals/runtime unverified")
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
