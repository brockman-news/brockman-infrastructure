{
  description = "Infrastructure for brockman.news";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-26.05";
    brockman.url = "github:kmein/brockman";
    brockman.inputs.nixpkgs.follows = "nixpkgs";
    brockman-site.url = "github:brockman-news/brockman-site";
    brockman-site.inputs.nixpkgs.follows = "nixpkgs";
    brockman-api.url = "github:brockman-news/brockman-api";
    brockman-api.inputs.nixpkgs.follows = "nixpkgs";
    brainmelter.url = "github:krebs/brainmelter";
    brainmelter.inputs.nixpkgs.follows = "nixpkgs";
    go-shortener.url = "github:brockman-news/go-shortener";
    go-shortener.inputs.nixpkgs.follows = "nixpkgs";
    clan-core.url = "git+https://git.clan.lol/clan/clan-core";
    clan-core.inputs.nixpkgs.follows = "nixpkgs";
    # tracks master: releases are rare and lag behind bridge fixes (e.g. YouTube)
    rss-bridge.url = "github:RSS-Bridge/rss-bridge";
    rss-bridge.flake = false;
  };

  outputs = inputs@{ self, nixpkgs, clan-core, ... }: let
    clan = clan-core.lib.clan {
      inherit self;
      specialArgs = {inherit inputs;};
      inventory.meta.name = "brockman";

      machines = {
        brockman = {
          nixpkgs.hostPlatform = "aarch64-linux";
          imports = [
            systems/brockman/configuration.nix
            inputs.brainmelter.nixosModules.brainmelter
            {
              services.brainmelter = {
                enable = false;
                hostname = "brainmelter.brockman.news";
              };
            }
            {
              system.autoUpgrade = {
                enable = true;
                # self.outPath would rebuild the already-deployed config; pull master so pushes (incl. lock bumps) get deployed
                flake = "github:brockman-news/brockman-infrastructure";
                flags = [
                  "--print-build-logs"
                ];
                dates = "02:00";
                randomizedDelaySec = "45min";
              };
            }
          ];
        };
      };
    };
  in {
    clan = clan.config;
    inherit (clan.config) clanInternals nixosConfigurations;
    devShells."x86_64-linux".default = nixpkgs.legacyPackages.x86_64-linux.mkShell {
      packages = [ clan-core.packages."x86_64-linux".clan-cli ];
    };
  };
}
