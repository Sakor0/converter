"""
archives.py - Pakowanie/rozpakowywanie ZIP i TAR(.gz). Czysty Python.
"""

import os
import tarfile
import zipfile

ARCHIVE_EXTS = {".zip", ".tar", ".gz", ".tgz"}


def pack_zip(output_path, input_paths):
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in input_paths:
            if os.path.isdir(p):
                parent = os.path.dirname(os.path.abspath(p))
                for root, _, files in os.walk(p):
                    for name in files:
                        full = os.path.join(root, name)
                        arcname = os.path.relpath(full, parent)
                        zf.write(full, arcname)
            else:
                zf.write(p, os.path.basename(p))


def unpack_zip(input_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    with zipfile.ZipFile(input_path) as zf:
        zf.extractall(output_dir)


def pack_tar(output_path, input_paths, gz=True):
    mode = "w:gz" if gz else "w"
    with tarfile.open(output_path, mode) as tf:
        for p in input_paths:
            tf.add(p, arcname=os.path.basename(p))


def unpack_tar(input_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    mode = "r:gz" if input_path.endswith((".gz", ".tgz")) else "r"
    with tarfile.open(input_path, mode) as tf:
        tf.extractall(output_dir)
