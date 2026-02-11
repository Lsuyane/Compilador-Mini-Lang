# Compilador Mini-Lang

## Install

### Linux

Simply run [`./scripts/install.sh`](./scripts/insttall.sh)

### Others

All the dependencies are listed at [`requirements.txt`](./requirements.txt). You can install then with it using `pip`.
See [`./scripts/install.sh`](./scripts/insttall.sh) for an example.

## Run

### Linux

You can use [`./scripts/run.sh`](./scripts/run.sh) or call [`compiler.py`](./src/compiler.py) directly.

### Others

Run:

```bash
python compiler.py --help
```

> [!TIP]
> Use `python compiler.py --help` for more options. See [`./scripts/run.sh`](./scripts/run.sh) for an example.
>
> In fact, you can call any of the compiler [modules](./src/modules/).
