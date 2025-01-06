{ inputs, pkgs, ... }:
{
  nixpkgs.overlays = [ inputs.brockman-site.overlays.default ];

  networking = {
    firewall.allowedTCPPorts = [80 443];
  };
  security.acme = {
    acceptTerms = true;
    defaults.email = "2210.brockman@cock.li";
  };
  services.nginx = {
    enable = true;
    virtualHosts."brockman.news" = {
      forceSSL = true;
      enableACME = true;
      root = pkgs.brockman-site;
    };
  };

  services.prometheus.exporters.nginx = {
    enable = false;
    port = 9113;
    openFirewall = true;
  };
}
