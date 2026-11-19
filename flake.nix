# fedtail for Nix: `nix run github:eugene-vereshchagin/fedtail`, or in a configuration
# `inputs.fedtail.url = "github:eugene-vereshchagin/fedtail";` and
# `fedtail.packages.${system}.default`. The package is packaging/nix/package.nix.
{
  description = "fedtail: a fediverse client for people who miss Point.im and Juick";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in {
      packages = forAll (pkgs: rec {
        fedtail = pkgs.callPackage ./packaging/nix/package.nix { };
        default = fedtail;
      });
      apps = forAll (pkgs: {
        default = {
          type = "app";
          program = "${self.packages.${pkgs.stdenv.hostPlatform.system}.default}/bin/fedtail";
        };
      });
    };
}
