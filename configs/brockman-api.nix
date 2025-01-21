{ inputs, config, ... }:
{
  imports = [ inputs.brockman-api.nixosModules.brockman-api ];

  services.nginx.virtualHosts."api.brockman.news" = {
    forceSSL = true;
    enableACME = true;
    locations."/".proxyPass = "http://127.0.0.1:${toString config.services.brockman-api.port}/";
  };

  services.brockman-api.enable = true;
}
