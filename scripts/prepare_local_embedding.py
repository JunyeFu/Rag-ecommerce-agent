"""Download the pinned public embedding model into the Hugging Face cache."""

from huggingface_hub import snapshot_download

MODEL_ID = "Qdrant/bge-small-zh-v1.5"
REVISION = "46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59"


def main() -> None:
    path = snapshot_download(
        repo_id=MODEL_ID,
        revision=REVISION,
    )
    print(f"ready: {MODEL_ID}@{REVISION}")
    print(path)


if __name__ == "__main__":
    main()
