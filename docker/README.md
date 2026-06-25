# Training image

Build from the repository root:

```bash
docker build -f docker/Dockerfile -t chinche-training:latest .
```

The image runs `training/train.py`. Data, output artifacts, and serialized
models are mounted at runtime by `ec2/run_training.sh`.

