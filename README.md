### BT Banking

Bank API integrations for ERPNext (ICICI statement sync)

Includes an ICICI Registration Status hybrid-encryption extension for India Banking
Connector v16. See [changes, configuration and validation](docs/icici-registration-hybrid.md).

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/Build-Together-LLC/btbanking --branch Bt
bench --site your-site install-app btbanking
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/btbanking
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
