{ pkgs, ... }:
{
  environment.systemPackages =
    [
      pkgs.htop
      pkgs.w3m
      pkgs.wget
      pkgs.unzip
      pkgs.p7zip
      pkgs.zip
      pkgs.iftop # interface bandwidth monitor
      pkgs.lsof # list open files
      # SHELL
      pkgs.fd # better find
      pkgs.tree
      pkgs.parallel # for parallel, since moreutils shadows task spooler
      pkgs.ripgrep # better grep
      pkgs.rlwrap
      pkgs.progress # display progress bars for pipes
      pkgs.file # determine file type
      pkgs.gdu # ncurses disk usage (ncdu is broken)
      pkgs.rmlint # remove duplicate files
      pkgs.ts
    ];

  environment.shellAliases = let
    take = pkgs.writers.writeDash "take" ''
      mkdir "$1" && cd "$1"
    '';
    cdt = pkgs.writers.writeDash "cdt" ''
      cd "$(mktemp -d)"
      pwd
    '';
    wcd = pkgs.writers.writeDash "wcd" ''
      cd "$(readlink "$(${pkgs.which}/bin/which --skip-alias "$1")" | xargs dirname)/.."
    '';
    where = pkgs.writers.writeDash "where" ''
      readlink "$(${pkgs.which}/bin/which --skip-alias "$1")" | xargs dirname
    '';
  in
    {
      take = "source ${take}";
      wcd = "source ${wcd}";
      where = "source ${where}";
      cdt = "source ${cdt}";
      vit = "$EDITOR $(mktemp)";
      mv = "${pkgs.coreutils}/bin/mv --interactive";
      rm = "${pkgs.coreutils}/bin/rm --interactive";
      cp = "${pkgs.coreutils}/bin/cp --interactive";
      cat = "${pkgs.bat}/bin/bat --theme=ansi --style=plain";
      l = "${pkgs.coreutils}/bin/ls --color=auto --time-style=long-iso --almost-all";
      ls = "${pkgs.coreutils}/bin/ls --color=auto --time-style=long-iso";
      ll = "${pkgs.coreutils}/bin/ls --color=auto --time-style=long-iso -l";
      la = "${pkgs.coreutils}/bin/ls --color=auto --time-style=long-iso --almost-all -l";
    }
    // {
      "ß" = "${pkgs.util-linux}/bin/setsid";
      ip = "${pkgs.iproute2}/bin/ip -c";
      # systemd
      s = "${pkgs.systemd}/bin/systemctl";
      us = "${pkgs.systemd}/bin/systemctl --user";
      j = "${pkgs.systemd}/bin/journalctl";
      uj = "${pkgs.systemd}/bin/journalctl --user";
    };
  }
