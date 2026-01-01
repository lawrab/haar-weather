{
  description = "Haar - Hyperlocal Scottish Weather Prediction System";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python311;
        pythonPackages = python.pkgs;
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            # Python interpreter
            python

            # System dependencies
            pkgs.sqlite
            pkgs.eccodes  # For cfgrib (GRIB2 file support)

            # Python development tools
            pythonPackages.pip
            pythonPackages.virtualenv
            pythonPackages.setuptools
            pythonPackages.wheel

            # CLI and UI
            pythonPackages.click
            pythonPackages.rich

            # Configuration
            pythonPackages.pydantic
            pythonPackages.pydantic-settings
            pythonPackages.python-dotenv

            # Data handling
            pythonPackages.pandas
            pythonPackages.numpy
            pythonPackages.xarray

            # Machine Learning
            pythonPackages.scikit-learn
            pythonPackages.lightgbm

            # HTTP and API
            pythonPackages.requests
            pythonPackages.tenacity

            # Database
            pythonPackages.sqlalchemy
            pythonPackages.alembic

            # Geospatial
            pythonPackages.pyproj

            # Logging
            pythonPackages.structlog

            # Visualization
            pythonPackages.matplotlib
            # Note: plotly removed due to nix build issues - install via pip when needed

            # Development dependencies
            pythonPackages.pytest
            pythonPackages.pytest-cov
            pythonPackages.black
            pythonPackages.ruff
            pythonPackages.mypy
            pythonPackages.ipython
            pythonPackages.jupyter

            # Additional useful tools
            pkgs.git
            pkgs.gh  # GitHub CLI
          ];

          shellHook = ''
            export HAAR_CONFIG="./config/haar.toml"
            export PYTHONPATH="$PWD:$PYTHONPATH"

            # Create data directories if they don't exist
            mkdir -p data/logs data/terrain data/cache

            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "🌫️  Haar Weather Prediction System"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo ""
            echo "Python version: $(python --version)"
            echo "Working directory: $PWD"
            echo "Config path: $HAAR_CONFIG"
            echo ""
            echo "📦 Installing package in development mode..."
            pip install -e . --quiet 2>/dev/null || echo "   Package will be installed on first use"
            echo ""
            echo "🚀 Ready to develop!"
            echo ""
            echo "Quick start:"
            echo "  haar --help           # Run the CLI"
            echo "  pytest                # Run tests"
            echo "  python -m haar.cli    # Run directly"
            echo ""
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
          '';
        };

        # Optional: Define the package itself
        packages.default = pythonPackages.buildPythonPackage {
          pname = "haar";
          version = "0.1.0";
          src = ./.;
          format = "pyproject";

          nativeBuildInputs = [
            pythonPackages.setuptools
            pythonPackages.wheel
          ];

          propagatedBuildInputs = [
            pythonPackages.click
            pythonPackages.rich
            pythonPackages.pydantic
            pythonPackages.pydantic-settings
            pythonPackages.python-dotenv
            pythonPackages.pandas
            pythonPackages.numpy
            pythonPackages.xarray
            pythonPackages.scikit-learn
            pythonPackages.lightgbm
            pythonPackages.requests
            pythonPackages.tenacity
            pythonPackages.sqlalchemy
            pythonPackages.alembic
            pythonPackages.pyproj
            pythonPackages.structlog
            pythonPackages.matplotlib
            # pythonPackages.plotly  # Removed - nix build issues
          ];
        };
      }
    );
}
