{
  description = "A very basic flake";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-24.05";
    brockman.url = "github:kmein/brockman";
    nixinate.url = "github:matthewcroughan/nixinate";
  };

  outputs = { self, nixpkgs, brockman, nixinate }: {
    apps.x86_64-linux = nixinate.nixinate.x86_64-linux self // {
      deploy-brockman = let
        pkgs = nixpkgs.legacyPackages.x86_64-linux;
      in {
        type = "app";
        program = toString (pkgs.writers.writeDash "deploy-brockman" ''
          exec ${pkgs.nix}/bin/nix run .#nixinate.ful \
          --log-format internal-json 2>&1 \
          | ${pkgs.nix-output-monitor}/bin/nom --json
        '');
      };
    };

    nixosConfigurations = {
      brockman = nixpkgs.lib.nixosSystem {
        system = "aarch64-linux";
        modules = [
          systems/brockman/configuration.nix
          brockman.nixosModule
          {
              _module.args.nixinate = {
                host = "brockman";
                sshUser = "root";
                buildOn = "remote";
                substituteOnTarget = true;
                hermetic = false;
              };
            }
        ];
      };
    };
  };
}
