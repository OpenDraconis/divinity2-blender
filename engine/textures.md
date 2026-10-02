# Textures

A texture is a NIF holding one `NiPersistentSrcTextureRendererData`: a DXT-compressed surface with mipmaps. It is a DDS minus the 128-byte header — NiPersistentSrcTextureRendererData nif

The header's four-character code comes from `pixel_format` (`FMT_DXT1`, `FMT_DXT3`, `FMT_DXT5` are `DXT1`, `DXT3`, `DXT5`); width and height are the top mipmap's; `num_mipmaps` is the mip count — NiPersistentSrcTextureRendererData nif

Mesh texture names say `.tga` or `.dds`; the file on disk is the same name with `.nif` in `Win32/Textures` — NiSourceTexture nif

Archives and Windows are case-insensitive, and a name may be a Windows path (`E:\Buildmanager\...\al_ruinedcorner_b_drkm.nif`); only the last segment, folded to lower case, is the key — StreamLib::CTexturePalette::ConvertPath @10dc3b0 decomp

The engine's known-name table is `Win32/Textures/Textures.bin`: u32 count, then per entry u32 length and `<name>.nif` — StreamLib::CTextureManager::ParsePersistentTextureCollection @10d3a70 decomp

A name not in the table draws `_black`, a 32x32 DXT1 with every block zero, so (0,0,0,1) at every mip; the map stays on the material and samples black — StreamLib::CTexturePalette::GetTextureWrapper @10dca00, DivStandardMaterial::GenerateDescriptor @1135a00 decomp

A terrain MegaTexture `.dds` and a `.tga` alpha map named in Terrain.xml are NIF textures like all others — NiPersistentSrcTextureRendererData nif

## Normal maps

The decode depends on the NiSourceTexture PixelFormat, never on content: DXT1 and DXT5 are NormalMapType 2 (x in alpha, y in green); DXN is type 1 (x in red); other formats are type 0, plain RGB — DivStandardMaterial::GenerateDescriptor @1135a00, DivStandardMaterial::HandleNormalMap @11316c0 decomp

n = c*2-1; z = sqrt(saturate(1 - x*x - y*y)); DXN rebuilds z from (r,g), DXT5 from (a,g); then xy *= WorldScale*LocalScale and the normal is normalize(T*x + B*y + N*z) — DivStandardMaterial::HandleNormalMap @11316c0 decomp

## Measured

10035 names in the known-name table — `python3 -c "import struct;print(struct.unpack_from('<I',open('$HOME/dv2-extract/Win32/Textures/Textures.bin','rb').read(),0)[0])"`
