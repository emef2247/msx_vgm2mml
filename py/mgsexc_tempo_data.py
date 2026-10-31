"""Tempo frame tables for MGSEXC.

Extracted from the reference compiler's observable output:
one 48-byte table per tempo for every tempo in 57..2047,
concatenated in tempo order, zlib-compressed, base85.
This is behavior data, kept until the generating formula
is fitted; see docs/mgsexc_design.md.
"""

import base64
import zlib

_B85 = (
    "c-rlne{SM15QVo=4iKbrACQ^@Ac6W9$Ka@Fue0%te}*`*yQEF%N9;HA-h2)zt*UCZx4)m)Tg^67rMLV2@8@UVmiASz{z!lDa=(}M"
    "rm50P-M-w->N{O?zF(JnkgJu?ODy+TB-I0^l@s~Azf5?&m{iPFOg6ve<Z7@-xmB+IPUcvD*tfT&brai4mBxfBhRo*DRcNU8o@sRT"
    "-TjijJ}=|1Twe9sSNOB<y2ttHA==kz=exaouhUe%uiGa*yO-6?`_A@f8J&iKBhD8eoJXW5PC4m9IhXjom`;L|gxT0#n&?!?eP(bL"
    "8=85a$SD><jO=6S&Ne(*sIw<W1IL#xb4ogMIFzZpZlArRZZ0qOMjwjICrU+?dz!Yi7kk!3!`VEVo?|8^ANi7(p3?ig%dO{gmlb-`"
    "OSjjq({3uNs^cX)>ebE_n(>L)sga4iZ~8bf<Eb+>ThDgE$&DuSI4ktkYZ&YX!Pu;@2Kn%!vmo!O?CgnxJ`}xoftN(u#N={oCD1U9"
    "yAb<9@ujEit>tcygDx7_P;JuYa?@&Kk^=8sc|Rs4v!ZHR?_7|&VNkQ=lsR7P-)#xqT<+W5NE_HM@^xFz>6>`7OO3s?H(_L>$=um@"
    "i!9)))SR;A-4`=T%STd{tlF4okw*(rZfK{=_1+cxBrD86a?Aq!(_XpvZ3_5i!Mv&R&7ys4nxoHlNjEaA<(p+|D92%GKYZEw(k!d3"
    "yk(=ZfVX0^)*{c$jXTChn#3GaQ^zm5Tl+ZDez?|6lJ@vj-j#>oDS4DF<yW-KQ<=x>A95JXj0<@?Tdt1D)a*O>CHvr3;WbIy=jLK<"
    "B%zCUQJf5x=GSxSQ|S}hFC!WpqrsPX4F={Xb8Sqr0`E#6uA`4+mx?^Q$}z~|yw0{;qc6p;WadAQZ{)YW-d5y?*|zexFdMdF5684!"
    "BfsH&(64aBjHfH)ttjJUE4ddt-J<_hdKfDcqZRVMs@ldRlaYKpFTtDa7xldnXDoiiOJXxk$<sWV9%3dYUytYY|F8J7jX(20(KiD="
    "X2}0HcNzXEULF0D`iCw|qo^51@Dn`s$7;Uxi1`)`3j7LqbUQk1@f+|eBN6%fa%~dhm@xzY+B};bw*FiU+x!In)p=9iLXjCcd2#MC"
    "JpP+Ji?zz-eo$S|W&(KlALFUi-&<p8te9DlLoD#{uf)3nJw5#*y(xG+eg$3|-%3hOPQH~~txhF$adrR?4-cOoaB*>QefOomh3s!6"
    "{p}PDGBG?nJp49zjl9trIXO8wc|k5si^t>f_-%XZ=;`U{>FIy4&q|}*P~hR=;o;#o%TuXTDwRt8<+cC2pkL}-&^teV2;kx2;o;%o"
    ";n&8qSS%Kc#bU8ucr}0Q-+t!LL_8jk$K&yMJRU#iO{cL5Y#}EnCnqN-CnqN-Ctq7`ik-Q(O<Ff;QwSa&9v&VZ9v&VZ9v&Y4r+GG;"
    "&1SRNY&M(CX0zFB_Vc#+Hy8P*7%}ab5u}BOhlhuUhlhuUhlhuUhlhuUhliizTbGCvX~@aR$;rvd$;rvd$;rvd$;rvd$;rvd$)A}w"
    "-YSB}<MDVr9*@W4@pwEQkH_Qjcsw4D$K&z%ZF+4{6h%=KMNt$*Q4~c{6h%=KMNt$*Q4~c{6h+Zm)&GU%%OM`w(j)~Q9v&VZ9v&VZ"
    "9v&VZ9v&VZ9v&VZ9v&VZ9v&VZ9v&VZ9v&VZ9v&VZ9v&Y41^9n_FRyF"
)


def load_tables() -> dict[int, bytes]:
    blob = zlib.decompress(base64.b85decode(_B85))
    return {57 + i: blob[i * 48:(i + 1) * 48] for i in range(2047 - 57 + 1)}
