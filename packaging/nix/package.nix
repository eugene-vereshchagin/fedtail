# fedtail as a Nix package (flake.nix at the repository's root uses it): the Qt and the
# GTK windows, the terminal and the web interface, sync and languages. The version is
# fedtail/__init__.py's; the menu entry, the icon and the AppStream file come from
# packaging/desktop_files.py.
{ lib, python3Packages, qt6, gtk4, libadwaita, gobject-introspection, wrapGAppsHook4 }:

let
  init = builtins.readFile ../../fedtail/__init__.py;
  version = builtins.head (builtins.match ''.*__version__ = "([^"]+)".*'' init);
in
python3Packages.buildPythonApplication {
  pname = "fedtail";
  inherit version;
  pyproject = true;

  src = lib.cleanSourceWith {
    src = ../..;
    filter = path: _type:
      let rel = lib.removePrefix (toString ../..) (toString path); in
      !(lib.any (p: lib.hasPrefix p rel) [ "/android" "/tmp" "/NOTES" "/build" "/dist" ]);
  };

  build-system = [ python3Packages.setuptools ];

  dependencies = with python3Packages; [
    requests
    pyside6
    pygobject3
    textual
    pillow
    cryptography
    langdetect
    pysocks
  ];

  nativeBuildInputs = [ qt6.wrapQtAppsHook wrapGAppsHook4 gobject-introspection ];
  buildInputs = [
    qt6.qtbase qt6.qtwayland qt6.qtsvg qt6.qtimageformats qt6.qtmultimedia
    gtk4 libadwaita
  ];

  # one wrapper with both toolkits' paths
  dontWrapQtApps = true;
  dontWrapGApps = true;
  preFixup = ''
    makeWrapperArgs+=("''${qtWrapperArgs[@]}" "''${gappsWrapperArgs[@]}")
  '';

  postInstall = ''
    ${python3Packages.python.interpreter} packaging/desktop_files.py $out
  '';

  pythonImportsCheck = [ "fedtail" "fedtail.core" ];
  doCheck = false; # the tests run in fedtail's own CI

  meta = {
    description = "Fediverse client for people who miss Point.im and Juick";
    homepage = "https://github.com/eugene-vereshchagin/fedtail";
    license = lib.licenses.gpl3Plus;
    mainProgram = "fedtail";
    platforms = lib.platforms.linux;
  };
}
