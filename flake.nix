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
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            # Python interpreter
            python

            # System dependencies (required by Python packages)
            pkgs.sqlite
            pkgs.eccodes  # For cfgrib (GRIB2 file support)
            pkgs.stdenv.cc.cc.lib  # libstdc++ for numpy/pandas

            # Development tools
            pkgs.git
            pkgs.gh  # GitHub CLI
          ];

          shellHook = ''
            export HAAR_CONFIG="./config/haar.toml"
            export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH"

            # Create data directories if they don't exist
            mkdir -p data/logs data/terrain data/cache

            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "🌫️  Haar Weather Prediction System"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo ""
            echo "Python version: $(python --version)"
            echo "Working directory: $PWD"
            echo ""

            # Auto-create and activate venv if it doesn't exist
            if [ ! -d ".venv" ]; then
              echo "📦 Creating virtual environment..."
              python -m venv .venv
            fi

            source .venv/bin/activate

            # Install package if not already installed
            if ! python -c "import haar" 2>/dev/null; then
              echo "📦 Installing package in development mode..."
              pip install -e ".[dev]" --quiet
            fi

            echo ""
            echo "🚀 Ready to develop!"
            echo ""
            echo "Quick start:"
            echo "  haar --help           # Run the CLI"
            echo "  haar dashboard        # Launch web dashboard"
            echo "  pytest                # Run tests"
            echo ""
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
          '';
        };
      }
    );
}
