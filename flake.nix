{
  description = "Infrastructure for brockman.news";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-25.05";
    brockman.url = "github:kmein/brockman";
    brockman.inputs.nixpkgs.follows = "nixpkgs";
    brockman-site.url = "github:brockman-news/brockman-site";
    brockman-site.inputs.nixpkgs.follows = "nixpkgs";
    brockman-api.url = "github:brockman-news/brockman-api";
    brockman-api.inputs.nixpkgs.follows = "nixpkgs";
    go-shortener.url = "github:brockman-news/go-shortener";
    go-shortener.inputs.nixpkgs.follows = "nixpkgs";
    clan-core.url = "git+https://git.clan.lol/clan/clan-core";
    clan-core.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = inputs@{ self, nixpkgs, clan-core, ... }: let
    clan = clan-core.lib.buildClan {
      inherit self;
      specialArgs = {inherit inputs;};
      inventory.meta.name = "brockman";

      machines = {
        brockman = {
          nixpkgs.hostPlatform = "aarch64-linux";
          imports = [ systems/brockman/configuration.nix ];
        };
      };
    };
  in {
    devShells."x86_64-linux".default = nixpkgs.legacyPackages.x86_64-linux.mkShell {
      packages = [ clan-core.packages."x86_64-linux".clan-cli ];
    };

    nixosConfigurations = clan.nixosConfigurations;
    inherit (clan) clanInternals;
  };
}
