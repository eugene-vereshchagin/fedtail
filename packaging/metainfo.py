"""The AppStream file (online.dmesg.fedtail.metainfo.xml): what software centres (GNOME
Software, Discover, Flathub) say about fedtail — its name, what it is, its licence, its
releases. One text for every package that installs it (Flatpak, RPM, Arch, AppImage):

    python3 packaging/metainfo.py out.xml     # → out.xml (stdout without an argument)

The releases are CHANGELOG.md's dated headings (`## X.Y.Z — date`), the newest first;
"What's next" isn't one yet. `appstreamcli validate` checks the file in CI's packages.
"""

import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fedtail.version import APP_ID, NAME  # noqa: E402

HOMEPAGE = "https://github.com/eugene-vereshchagin/fedtail"
RELEASES = 12  # this many of the newest in the file

SUMMARY = {"en": "Read and write to the fediverse, whole threads as trees",
           "ru": "Читать и писать в федиверс, обсуждения целиком деревом"}
ABOUT = {
    "en": ("A desktop client for GoToSocial, Mastodon, Akkoma and anything else that "
           "speaks the Mastodon API, for people who miss Point.im and Juick.",
           "Whole threads as trees where every reply shows what it answers, lanes that "
           "never jump, posts read where they were left. Every behaviour is an option in "
           "a commented config file; the author's way is only a preset."),
    "ru": ("Клиент для GoToSocial, Mastodon, Akkoma и всего, что говорит на Mastodon API, "
           "для тех, кому не хватает Point.im и Juick.",
           "Обсуждения целиком деревом, где у каждого ответа видно, на что он отвечает; "
           "ленты, которые не прыгают; прочитанное остаётся там, где оставили. Каждое "
           "поведение — параметр в файле настроек с пояснениями; авторский вариант — лишь "
           "набор по умолчанию."),
}


def releases(changelog):
    """[(version, date)] of the CHANGELOG's dated headings, the newest first."""
    return re.findall(r"^## (\d+\.\d+\.\d+) — (\d{4}-\d{2}-\d{2})", changelog, re.M)


def text(changelog=None):
    changelog = changelog if changelog is not None else \
        (ROOT / "CHANGELOG.md").read_text("utf-8")

    def tr(tag, words, indent):
        """One line per language: English plain, the others with xml:lang."""
        lines = []
        for lang, w in words.items():
            attr = "" if lang == "en" else f' xml:lang="{lang}"'
            lines.append(f"{' ' * indent}<{tag}{attr}>{escape(w)}</{tag}>")
        return "\n".join(lines)

    about = "\n".join(
        tr("p", {lang: paras[i] for lang, paras in ABOUT.items()}, 4)
        for i in range(2))
    rel = "\n".join(f'    <release version="{v}" date="{d}"/>'
                    for v, d in releases(changelog)[:RELEASES])
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- made by packaging/metainfo.py -->
<component type="desktop-application">
  <id>{APP_ID}</id>
  <name>{NAME}</name>
{tr("summary", SUMMARY, 2)}
  <metadata_license>CC0-1.0</metadata_license>
  <project_license>GPL-3.0-or-later</project_license>
  <developer id="io.github.eugene-vereshchagin">
    <name>Eugene Vereshchagin</name>
  </developer>
  <description>
{about}
  </description>
  <launchable type="desktop-id">{APP_ID}.desktop</launchable>
  <provides>
    <binary>fedtail</binary>
  </provides>
  <url type="homepage">{HOMEPAGE}</url>
  <url type="bugtracker">{HOMEPAGE}/issues</url>
  <url type="vcs-browser">{HOMEPAGE}</url>
  <categories>
    <category>Network</category>
    <category>Chat</category>
  </categories>
  <keywords>
    <keyword>mastodon</keyword>
    <keyword>gotosocial</keyword>
    <keyword>fediverse</keyword>
  </keywords>
  <content_rating type="oars-1.1">
    <content_attribute id="social-chat">intense</content_attribute>
    <content_attribute id="social-info">mild</content_attribute>
    <content_attribute id="social-contacts">intense</content_attribute>
  </content_rating>
  <supports>
    <control>pointing</control>
    <control>keyboard</control>
  </supports>
  <releases>
{rel}
  </releases>
</component>
"""


def write(path):
    Path(path).write_text(text(), "utf-8")
    return Path(path)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(write(sys.argv[1]))
    else:
        sys.stdout.write(text())
