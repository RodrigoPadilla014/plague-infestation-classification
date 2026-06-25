# EC2 instance

Record the active reusable host in `ec2/config.env`:

```bash
export CHINCHE_INSTANCE_ID="i-..."
export CHINCHE_INSTANCE_TYPE="m5.xlarge"
```

Recommended initial host:

```text
4 vCPU
16 GiB RAM
50 GiB gp3
Ubuntu 24.04 x86_64
```

Required commands are `aws`, `docker`, `flock`, and `timeout`. Attach an IAM
instance profile with read access to the dataset prefix, write access to the
experiment prefix, and ECR pull access.

The host type is deliberately not hardcoded. If Optuna or a larger dataset
requires more resources, update the EC2 instance and the corresponding
`CHINCHE_INSTANCE_TYPE`, `CHINCHE_CPUS`, and `CHINCHE_MEMORY` values.

