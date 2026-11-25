# Fonts

Bundled, open-licence (SIL OFL 1.1) fonts, latin subset, taken from the Fontsource packages. The editor preview
and the renderer both load them through `fonts.css`, so a look can name any of these:

| Family | Use | Weights |
|---|---|---|
| Inter | clean sans, captions and UI | 400–900 |
| Poppins | geometric sans, bold lowercase captions | 500–800 |
| Bricolage Grotesque | characterful sans | 600–800 |
| Fraunces | warm serif with italics (Olga's brand serif) | 400, 600, 700, 900 + italics |
| Instrument Serif | editorial serif with italic | 400 + italic |
| Anton | condensed caps for big titles | 400 |
| Caveat | handwriting | 500, 700 |
| Allura | script | 400 |

To add another: put its `.woff2` here and add an `@font-face` line to `fonts.css` with the family name you
want to use in your look.
