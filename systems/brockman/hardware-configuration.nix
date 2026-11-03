{ modulesPath, ... }:
{
  imports = [ (modulesPath + "/profiles/qemu-guest.nix") ];

  boot.loader.grub = {
    efiSupport = true;
    efiInstallAsRemovable = true;
    device = "nodev";
    # the ESP is 253M and one kernel+initrd is ~80M: 3 generations filled it and blocked switch-to-configuration
    configurationLimit = 2;
  };

  fileSystems."/boot" = { device = "/dev/disk/by-uuid/34A7-AE07"; fsType = "vfat"; };
  boot.initrd.availableKernelModules = [ "ata_piix" "uhci_hcd" "xen_blkfront" ];
  boot.initrd.kernelModules = [ "nvme" ];
  fileSystems."/" = { device = "/dev/sda1"; fsType = "ext4"; };
}
