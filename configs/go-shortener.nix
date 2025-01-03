{ config, inputs, ... }:
let
  shortenerEndpoint = "go.brockman.news";
in {
  imports = [ inputs.go-shortener.nixosModules.default ];

  services.nginx.virtualHosts = {
    ${shortenerEndpoint} = {
      locations."/".proxyPass = "http://127.0.0.1:${toString config.services.go-shortener.port}/";
    };
  };

  # TODO serve stats of
  # redis-go-shortener DBSIZE
  # redis-go-shortener INFO memory

  services.go-shortener = {
    enable = true;
    endpoint = "http://${shortenerEndpoint}";
    port = 8888;
  };

  services.brockman.config.shortener = "http://${shortenerEndpoint}";
}
