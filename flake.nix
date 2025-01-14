{
  description = "Infrastructure for brockman.news";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-24.11";
    brockman.url = "github:kmein/brockman";
    nixinate.url = "github:matthewcroughan/nixinate";
    stockholm.url = "github:krebs/stockholm";
    brockman-site.url = "github:brockman-news/brockman-site";
    go-shortener.url = "github:brockman-news/go-shortener";
    clan-core.url = "git+https://git.clan.lol/clan/clan-core";
    clan-core.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = inputs@{ self, nixpkgs, brockman, nixinate, stockholm, brockman-site, clan-core, go-shortener }: let
    clan = clan-core.lib.buildClan {
      directory = self;
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
