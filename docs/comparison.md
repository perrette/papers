# Comparison with other tools

## Why not JabRef, Zotero or Mendeley (or...) ?

- JabRef (2.10) is nice, light-weight, but is not so good at managing PDFs.
- Zotero (5.0) features excellent PDF import capability, but it needs to be done
  manually one by one and is a little slow. Not very flexible.
- Mendeley (1.17) is perfect at automatically extracting metadata from
  downloaded PDFs and managing your PDF library, but it is not open source, and
  many issues remain (own experience, Ubuntu 14.04, Desktop Version 1.17):
    - very unstable
    - PDF automatic naming is too verbose, and sometimes the behaviour is
      unexpected (some PDFs remain in an obscure Downloaded folder, instead of
      in the main collection)
    - somewhat heavy (it offers functions of online syncing, etc)
    - poor search capability (related to the point above)

Above-mentioned issues will with no doubt be improved in future releases, but
they are a starting point for this project. Anyway, a command-line tool is per
se a good idea for faster development, as noted
[here](https://forums.zotero.org/discussion/43386/zotero-cli-version), but so
far I could only find zotero clients for their online API (like
[pyzotero](https://github.com/urschrei/pyzotero) or
[zotero-cli](https://github.com/jbaiter/zotero-cli)). Please contact me if you
know another interesting project.
