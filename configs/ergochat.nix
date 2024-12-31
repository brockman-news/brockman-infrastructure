{
  networking.firewall.allowedTCPPorts = [6667];

  services.ergochat.enable = true;
  services.ergochat.openFilesLimit = 16384;
  services.ergochat.settings = {
    oper-classes = {
      chat-moderator = {
        title = "Chat Moderator";
        capabilities = [
          "kill"      # disconnect user sessions
          "ban"       # ban IPs, CIDRs, NUH masks, and suspend accounts (UBAN / DLINE / KLINE)
          "nofakelag" # exempted from "fakelag" restrictions on rate of message sending
          "relaymsg"  # use RELAYMSG in any channel (see the `relaymsg` config block)
          "vhosts"    # add and remove vhosts from users
          "sajoin"    # join arbitrary channels, including private channels
          "samode"    # modify arbitrary channel and user modes
          "snomasks"  # subscribe to arbitrary server notice masks
          "roleplay"  # use the (deprecated) roleplay commands in any channel
        ];
      };
    # server admin: has full control of the ircd, including nickname and
    # channel registrations
    "server-admin" = {
        # title shown in WHOIS
        title = "Server Admin";
        # oper class this extends from
        extends = "chat-moderator";

        # capability names
        capabilities = [
          "rehash"       # rehash the server, i.e. reload the config at runtime
          "accreg"       # modify arbitrary account registrations
          "chanreg"      # modify arbitrary channel registrations
          "history"      # modify or delete history messages
          "defcon"       # use the DEFCON command (restrict server capabilities)
          "massmessage"  # message all users on the server
        ];
      };
    };
    opers.admin.password = "$2a$04$egKfWWPKeFPrCXuJfTElgugrOSwFFitYJR5BnDwngNP1gCUfego6W";
    opers.admin.class = "server-admin";
    opers.admin.hidden = true;
    limits.nicklen = 100;
    limits.identlen = 100;
    history.enabled = false;
  };
}
