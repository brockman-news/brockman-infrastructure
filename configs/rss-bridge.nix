let
  rss-bridge-url = "rss-bridge.brockman.news";
  rss-bridge-endpoint = "https://${rss-bridge-url}";
in
{
  services.rss-bridge = {
    enable = true;
    config.system.enabled_bridges = [ "*" ];
  };
  services.nginx.virtualHosts = {
    rss-bridge = {
      serverAliases = [
        rss-bridge-url
      ];
    };
  };

  /*
  krebs.reaktor2.api = {
    hostname = "localhost";
    port = "6667";
    nick = "api";
    API.listen = "inet://127.0.0.1:7777";
    plugins = [
      {
        plugin = "register";
        config = {
          channels = [
            "#all"
          ];
        };
      }
    ];
  };
  krebs.reaktor2.news = let
    name = "candyman";
  in {
    hostname = "localhost";
    port = "6667";
    nick = name;
    plugins = [
      {
        plugin = "register";
        config = {
          channels = [
            "#all"
            "#aluhut"
            "#news"
            "#lasstube"
          ];
        };
      }
      {
        plugin = "system";
        config = {
          hooks.PRIVMSG = [
            {
              activate = "match";
              pattern = "^${name}:\\s*(\\S*)(?:\\s+(.*\\S))?\\s*$";
              command = 1;
              arguments = [2];
              commands = {
                add-reddit.filename = pkgs.writers.writeDash "add-reddit" ''
                  set -euf
                  if [ "$#" -ne 1 ]; then
                    echo 'usage: ${name}: add-reddit $reddit_channel'
                    exit 1
                  fi
                  reddit_channel=$(echo "$1" | ${pkgs.jq}/bin/jq -Rr '[match("(\\S+)\\s*";"g").captures[].string][0]')
                  echo "brockman: add r_$reddit_channel ${rss-bridge-endpoint}?action=display&bridge=Reddit&context=single&r=$reddit_channel&format=Atom"
                '';
                add-telegram.filename = pkgs.writers.writeDash "add-telegram" ''
                  set -euf
                  if [ "$#" -ne 1 ]; then
                    echo 'usage: ${name}: add-telegram $telegram_user'
                    exit 1
                  fi
                  telegram_user=$(echo "$1" | ${pkgs.jq}/bin/jq -Rr '[match("(\\S+)\\s*";"g").captures[].string][0]')
                  echo "brockman: add t_$telegram_user ${rss-bridge-endpoint}/?action=display&bridge=Telegram&username=$telegram_user&format=Mrss"
                '';
                add-youtube.filename = pkgs.writers.writeDash "add-youtube" ''
                  set -euf
                  if [ "$#" -ne 1 ]; then
                    echo 'usage: ${name}: add-youtube $nick $channel/video/stream/id'
                    exit 1
                  fi
                  youtube_nick=$(echo "$1" | ${pkgs.jq}/bin/jq -Rr '[match("(\\S+)\\s*";"g").captures[].string][0]')
                  youtube_url=$(echo "$1" | ${pkgs.jq}/bin/jq -Rr '[match("(\\S+)\\s*";"g").captures[].string][1]')
                  if [ ''${#youtube_url} -eq 24 ]; then
                    youtube_id=$youtube_url
                  else
                    youtube_id=$(${pkgs.yt-dlp}/bin/yt-dlp --max-downloads 1 -j "$youtube_url" | ${pkgs.jq}/bin/jq -r '.channel_id')
                  fi
                  echo "brockman: add yt_$youtube_nick ${rss-bridge-endpoint}/?action=display&bridge=Youtube&context=By+channel+id&c=$youtube_id&duration_min=&duration_max=&format=Mrss"
                '';
                add-twitch.filename = pkgs.writers.writeDash "add-twitch" ''
                  set -euf
                  if [ "$#" -ne 1 ]; then
                    echo 'usage: ${name}: add-twitch $handle'
                    exit 1
                  fi
                  twitch_nick=$(echo "$1" | ${pkgs.jq}/bin/jq -Rr '[match("(\\S+)\\s*";"g").captures[].string][0]')
                  echo "brockman: add twitch_$twitch_nick ${rss-bridge-endpoint}/?action=display&bridge=Twitch&channel=$twitch_nick&type=all&format=Atom"
                '';
                add-twitter.filename = pkgs.writers.writeDash "add-twitter" ''
                  set -euf
                  if [ "$#" -ne 1 ]; then
                    echo 'usage: ${name}: add-twitter $handle'
                    exit 1
                  fi
                  twitter_nick=$(echo "$1" | ${pkgs.jq}/bin/jq -Rr '[match("(\\S+)\\s*";"g").captures[].string][0]')
                  echo "brockman: add tw_$twitter_nick ${rss-bridge-endpoint}/?action=display&bridge=Twitter&context=By+username&u=$twitter_nick&norep=on&noretweet=on&nopinned=on&nopic=on&format=Atom"
                '';
                search.filename = pkgs.writers.writeDash "search" ''
                  set -euf
                  if [ "$#" -ne 1 ]; then
                    echo 'usage: ${name}: search $searchterm'
                    exit 1
                  fi
                  searchterm=$(echo "$1" | ${pkgs.jq}/bin/jq -Rr '[match("(\\S+)\\s*";"g").captures[].string][0]')
                  ${pkgs.curl}/bin/curl -Ss "https://feedsearch.dev/api/v1/search?url=$searchterm&info=true&favicon=false" |
                    ${pkgs.jq}/bin/jq '.[].url'
                '';
              };
            }
          ];
        };
      }
    ];
  };
  */
}
