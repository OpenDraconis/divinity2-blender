# The animation set (`.kfm`)

A KFM ties a family together: which skeleton its clips were authored for,
which `.kf` files hold them, and how one animation gives way to another.
Divinity II ships 121 of them, one per family and weapon set —
`Human_F_Base.kfm`, `Human_F_Base_BOW.kfm`, `Human_F_Melee_2HSW.kfm` — and
bundles a copy of each character's own into its `.cat` as
`MdlMan::CAMDataEntry`, which `nif.xml` labels "a KFM without header".

All 121 are version **2.2.0.0b** (`0x0202000B`).

## The format is described, not guessed

NifTools describes KFM the same way it describes NIF: one XML file,
[`niftools/kfmxml`](https://github.com/niftools/kfmxml). Sixty-nine lines.

```
Kfm          header string, unknown byte, NIF file name, master, 2 ints,
             2 floats, animation count, animations, 1 int
Animation    event code, KF file name, index, transition count, transitions
Transition   animation, type, and — unless bare — duration, intermediate
             animations, text key pair count
```

The header reads straight off: `.\Skeleton.nif`, master `Scene Root`.

**An animation has no name at this version.** `kfm.xml` marks the `Name`
field `ver2="16927488"`, so it was dropped after 1.2.4b. What identifies an
animation here is an integer event code. Clip names still come from the
`NiControllerSequence` blocks inside the `.kf`.

## Where Divinity II parts company with the description

`kfm.xml` says a transition carries its payload unless its type is 5. In this
game type **4 is bare as well**. Measured over all 121 sets:

| rule | sets that parse to the exact last byte |
|---|---|
| bare = {5}, as `kfm.xml` states | 77 of 121 |
| bare = {4, 5} | **105 of 121** |

Type counts across those 105: `5` appears 27,858 times, `4` 108 times, `2`
598 times, `1` four times. Types 1 and 2 do carry the payload — `Troll.kfm`
has a type 1 with a 0.4 s duration, and reading it as bare derails the rest
of the file.

The remaining 16 stop partway through a transition list. All 16 are the
player's own sets and three creatures, which are the largest and most
transitioned. Rather than fail them, the reader stops where the bytes stop
agreeing and says so (`AnimationSet.complete`), which costs nothing here:
the header and the file references come first, and after a scan of the
unread tail **no set loses a `.kf` reference**.

## What it is used for

- the `.kf` files a character actually uses, instead of scraping filenames
  out of the bytes with a regular expression.
