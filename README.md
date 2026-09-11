# projects

A workspace repository for assorted projects.

## About

This repository is a starting point. Each project lives in its own
subdirectory with its own README describing what it does and how to
run it.

## Getting started

```bash
git clone https://github.com/f1133/projects.git
cd projects
```

## Layout

```
projects/
├── README.md
├── hardware/
│   └── g431-can-actuator/   # STM32G431 CAN-FD actuator node (KiCad)
└── <project-name>/          # one directory per project
```

## Projects

| Project | Description |
|---|---|
| [`hardware/g431-can-actuator`](hardware/g431-can-actuator) | KiCad schematic for a CAN-FD BLDC actuator node: STM32G431CBT6 + DRV8311S three-phase driver, one board per actuator, daisy-chained on a single CAN bus. |

## License

No license has been chosen yet. Until one is added, all rights are
reserved by the repository owner.
