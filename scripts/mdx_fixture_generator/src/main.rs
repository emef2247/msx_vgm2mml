// SPDX-License-Identifier: MIT
// External fixture-generation utility. The converter does not depend on it.
use std::{env, fs, path::Path, fmt::Write};
use soundlog::mdx::{convert::{to_vgm_document, MdxToVgmOptions}, package::MdxPackage};

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    if args.len() != 4 && args.len() != 6 {
        return Err("usage: mdx-fixture-generator INPUT.mml OUTPUT.mdx OUTPUT.vgm [--max-ticks N] | --from-mdx INPUT.mdx OUTPUT.vgm [--max-ticks N] | --inspect-mdx INPUT.mdx OUTPUT.csv".into());
    }
    if args[1] == "--inspect-mdx" {
        if args.len() != 4 { return Err("--inspect-mdx takes only INPUT.mdx OUTPUT.csv".into()); }
        let package = MdxPackage::parse(&fs::read(&args[2])?, None)?;
        let mut csv = String::from("voice_id,algorithm,feedback,op");
        for name in ["m1", "m2", "c1", "c2"] {
            for field in ["ar", "d1r", "d2r", "rr", "d1l", "tl", "ks", "mul", "dt1", "dt2", "am_enabled"] {
                write!(&mut csv, ",{name}_{field}")?;
            }
        }
        csv.push('\n');
        for tone in &package.mdx.tone_bank.tones {
            write!(&mut csv, "{},{},{},{}", tone.voice_number, tone.con, tone.fl, tone.op)?;
            for op in tone.operators {
                write!(&mut csv, ",{},{},{},{},{},{},{},{},{},{},{}",
                       op.ar, op.dr, op.sr, op.rr, op.sl, op.ol, op.ks, op.ml, op.dt1, op.dt2, op.ame)?;
            }
            csv.push('\n');
        }
        if let Some(parent) = Path::new(&args[3]).parent() { fs::create_dir_all(parent)?; }
        fs::write(&args[3], csv)?;
        return Ok(());
    }
    let mut options = MdxToVgmOptions { loop_count: Some(1), ..Default::default() };
    if args.len() == 6 {
        if args[4] != "--max-ticks" { return Err("Unknown option".into()); }
        let limit: u32 = args[5].parse()?;
        if limit == 0 { return Err("max-ticks must be positive".into()); }
        options.max_ticks = Some(limit);
    }
    let from_mdx = args[1] == "--from-mdx";
    let package = if from_mdx {
        MdxPackage::parse(&fs::read(&args[2])?, None)?
    } else {
        let text = fs::read_to_string(&args[1])?;
        let parsed = mmlx::mdx::parse(&text)?;
        MdxPackage { mdx: mmlx::mdx::compile(&parsed)?, pdx: None }
    };
    if package.pdx_name().is_some_and(|n| !n.is_empty()) {
        return Err("This FM-only fixture utility does not load PDX samples".into());
    }
    if !package.pcm_references().is_empty() {
        return Err("PCM notes are not allowed in these OPM fixtures".into());
    }
    if !from_mdx {
        // Keep a compiled MDX available even if the external replay fails.
        let mdx_bytes = package.to_mdx_bytes()?;
        if let Some(parent) = Path::new(&args[2]).parent() { fs::create_dir_all(parent)?; }
        fs::write(&args[2], mdx_bytes)?;
    }
    let vgm_bytes: Vec<u8> = to_vgm_document(&package, &options)?.into();
    if let Some(parent) = Path::new(&args[3]).parent() { fs::create_dir_all(parent)?; }
    fs::write(&args[3], vgm_bytes)?;
    Ok(())
}

fn main() {
    if let Err(error) = run() { eprintln!("{error}"); std::process::exit(1); }
}
