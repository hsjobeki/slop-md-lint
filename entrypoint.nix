# manifest dependencies, injected by the nix/importer.nix
# ↓ dependencies controlled by mana
{ nixpkgs }:
#
# - to test: nix repl -f default.nix
# - to pass an explicit system 'import default.nix { system = "x86_64-linux"; }'
#
# ↓ your parameters
{ system ? builtins.currentSystem, ... }:
let
  pkgs = nixpkgs { inherit system; };
  fs = pkgs.lib.fileset;
  src = fs.toSource {
    root = ./.;
    fileset = fs.unions [
      ./slop_md_lint.py
      ./tests
    ];
  };
in
{
  slop-md-lint = pkgs.python3.pkgs.buildPythonApplication {
    pname = "slop-md-lint";
    version = "0.1.0";
    pyproject = false;

    inherit src;

    installPhase = ''
      install -Dm755 slop_md_lint.py $out/bin/slop-md-lint
    '';

    meta = {
      description = "Detect probable AI-generated slop in markdown documentation";
      license = pkgs.lib.licenses.mit;
      mainProgram = "slop-md-lint";
    };
  };

  checks.tests = pkgs.runCommand "slop-md-lint-tests" {
    nativeBuildInputs = [ (pkgs.python3.withPackages (ps: [ ps.pytest ])) ];
  } ''
    cp -r ${src}/* .
    python3 -m pytest tests/test_slop_md_lint.py -v
    touch $out
  '';
}
