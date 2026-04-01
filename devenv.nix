{
  pkgs,
  lib,
  config,
  inputs,
  ...
}:

{
  dotenv.enable = true;

  # https://devenv.sh/basics/
  env.GREET = "LifeOS";

  # https://devenv.sh/packages/
  packages = [
    pkgs.zlib
  ];

  # https://devenv.sh/languages/
  languages.python = {
    enable = true;
    uv = {
      enable = true;
      sync.enable = true;
    };
  };

  # devenv up starts all processes
  processes = {
    falkordb = {
      exec = ''
        cleanup() {
          docker stop falkordb-dev 2>/dev/null || true
        }
        trap cleanup EXIT INT TERM

        docker stop falkordb-dev 2>/dev/null || true
        docker rm falkordb-dev 2>/dev/null || true

        # Current FalkorDB images persist Redis data under /var/lib/falkordb/data.
        docker run --rm \
          --name falkordb-dev \
          -p 6379:6379 \
          -p 3000:3000 \
          -v "${config.devenv.root}/.devenv/falkordb-data:/var/lib/falkordb/data" \
          falkordb/falkordb:latest \
          --appendonly yes
      '';
    };
  };

  enterShell = ''
    mkdir -p .devenv/falkordb-data
  '';

  env.LD_LIBRARY_PATH = lib.makeLibraryPath [
    pkgs.stdenv.cc.cc.lib
    pkgs.zlib
  ];

  # https://devenv.sh/processes/
  # processes.dev.exec = "${lib.getExe pkgs.watchexec} -n -- ls -la";

  # https://devenv.sh/services/
  # services.postgres.enable = true;

  # https://devenv.sh/scripts/
  scripts.hello.exec = ''
    echo hello from $GREET
  '';

  # https://devenv.sh/tasks/
  # tasks = {
  #   "myproj:setup".exec = "mytool build";
  #   "devenv:enterShell".after = [ "myproj:setup" ];
  # };

  # https://devenv.sh/tests/
  # enterTest = ''
  #   echo "Running tests"
  #   git --version | grep --color=auto "${pkgs.git.version}"
  # '';

  # https://devenv.sh/git-hooks/
  # git-hooks.hooks.shellcheck.enable = true;

  # See full reference at https://devenv.sh/reference/options/
}
