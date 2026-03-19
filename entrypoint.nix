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
      ./prompts
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

    installPhase = let
      python = pkgs.python3;
    in ''
      mkdir -p $out/lib/slop-md-lint/prompts
      cp slop_md_lint.py $out/lib/slop-md-lint/
      cp prompts/*.md $out/lib/slop-md-lint/prompts/

      mkdir -p $out/bin
      echo '#!${python}/bin/python3' > $out/bin/slop-md-lint
      echo 'import sys, runpy' >> $out/bin/slop-md-lint
      echo 'sys.argv[0] = "'"$out"'/lib/slop-md-lint/slop_md_lint.py"' >> $out/bin/slop-md-lint
      echo 'runpy.run_path(sys.argv[0], run_name="__main__")' >> $out/bin/slop-md-lint
      chmod +x $out/bin/slop-md-lint
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
