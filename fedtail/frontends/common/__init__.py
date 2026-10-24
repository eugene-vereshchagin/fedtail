"""What every graphical frontend does the same way, with no toolkit in it: which links
do what, which actions a post offers, the rules of writing a post, the command line.

Qt and GTK draw it; the decisions live here once (docs/en/dev/gtk.md, stage 0). Nothing in this
package imports a toolkit — a test checks.
"""
