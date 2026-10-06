"""Offline smoke for an installed wheel; run with `python -I` outside the checkout.

Exercises real document extraction and SQLite indexing, without a model/runtime.
This is packaging evidence, not inference-quality evidence.
"""

import os
import re
import sys
from importlib import resources
from pathlib import Path
from tempfile import TemporaryDirectory

import tre_llm
from tre_llm import config, paths
from tre_llm.documents.service import add_document, list_documents, remove_document, search
from tre_llm.registry import catalog
from tre_llm.storage import db


def main() -> None:
    # Never let an editable/source import turn a broken wheel into a passing test.
    package_path = Path(tre_llm.__file__).resolve()
    assert Path(sys.prefix).resolve() in package_path.parents, package_path
    print(f"Installed package: {package_path}")

    assert config.get("runtime", "llama_cpp_build")
    assert config.get("runtime", "ubuntu_x64_url")
    assert len(config.get("runtime", "ubuntu_x64_sha256")) == 64
    assert catalog(), "The wheel must include the model registry."
    webui = resources.files("tre_llm").joinpath("webui")
    index = webui.joinpath("index.html").read_text(encoding="utf-8")
    assets = re.findall(r'(?:src|href)="(/assets/[^"?#]+)"', index)
    assert assets, "The shipped UI must reference built assets."
    for asset in assets:
        assert webui.joinpath(asset.lstrip("/")).is_file(), asset
    assert any(asset.endswith(".js") for asset in assets), assets
    print(f"Shipped UI references {len(assets)} existing assets.")

    with TemporaryDirectory(prefix="tre-wheel-smoke-") as directory:
        root = Path(directory)
        os.environ["TRE_LLM_HOME"] = str(root / "home")
        paths.reset_caches()
        paths.ensure_dirs()
        fixtures = [
            (
                "notes.md",
                "Điểm thi được đăng ở Đà Nẵng.\n".encode(),
                '"diem',
                "Điểm thi",
            ),
            (
                "notes.pdf",
                (Path(__file__).parent / "fixtures" / "notes.pdf").read_bytes(),
                "thu do",
                "Ha Noi",
            ),
        ]
        try:
            for name, content, query, excerpt in fixtures:
                document = root / name
                document.write_bytes(content)
                metadata = add_document(document)
                assert metadata["status"] == "indexed" and metadata["chunks"] >= 1
                hits = search(query)
                assert any(hit["document_id"] == metadata["id"] and excerpt in hit["text"] for hit in hits)
                assert remove_document(metadata["id"])
                assert not search(query)
                assert not list_documents()
                print(f"Ingest/search/delete passed: {name}")
        finally:
            db.reset_default()
            paths.reset_caches()
    print("Wheel smoke passed without model or runtime downloads.")


if __name__ == "__main__":
    main()
