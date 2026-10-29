"""All blueprint pages publish atomically, independently of ordinary products."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'py')]
import batch_vgm_to_mgs as batch
import export_vgm


def generated(folder,stem,texts):
    records=[]
    for index,text in enumerate(texts):
        name=stem+'.mml' if index==0 else stem+f'.part{index+1:02d}.mml'
        p=folder/'blueprint'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
        records.append(dict(path=str(p.resolve()),name=name,sha256=batch.file_digest(p)))
    return dict(blueprint=dict(status='success',path=records[0]['path'],sha256=records[0]['sha256'],files=records))


def old_package(package,stem='song'):
    package.mkdir(parents=True,exist_ok=True)
    first=package/'blueprint'/f'{stem}.mml';second=package/'blueprint'/f'{stem}.part02.mml'
    first.parent.mkdir();first.write_text('1 c4');second.write_text('2 d4')
    main=package/'tracks'/f'{stem}.vgm';main.parent.mkdir();main.write_bytes(b'old VGM')
    products={p.relative_to(package).as_posix():batch.file_digest(p) for p in (first,second,main)}
    state=dict(schema_version=1,entries={stem+'.vgm':dict(published=products)})
    manifest=package/'listening_manifest.json';batch.save_json(manifest,state)
    return products,state,first,second,main,manifest


def source_file(root,name='site/game/song.vgm'):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
    raw=bytearray(256);raw[:4]=b'Vgm '
    struct.pack_into('<I',raw,8,0x171);struct.pack_into('<I',raw,0x34,256-0x34)
    raw+=bytes.fromhex('61 df 02 66');struct.pack_into('<I',raw,4,len(raw)-4)
    p.write_bytes(raw);return p


class BlueprintBundleTests(unittest.TestCase):
    def test_all_generated_pages_are_validated_and_published_together(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder=root/'diag';folder.mkdir();package=root/'package';package.mkdir()
            report=generated(folder,'song',['1 c4','2 d4','3 e4'])
            self.assertEqual(len(batch.blueprint_products(report,folder,'song')),3)
            publications,deletions,products,status,detail,targets=batch.prepare_blueprints(report,folder,'song',package,{})
            self.assertEqual(status,'success');self.assertFalse(deletions);self.assertEqual(len(targets),3)
            state=dict(schema_version=1,entries={'song.vgm':dict(published=products)})
            batch.publish_bundle(publications,package/'listening_manifest.json',state,folder,deletions=deletions)
            self.assertEqual([p.name for p in targets],['song.mml','song.part02.mml','song.part03.mml'])
            self.assertEqual([p.read_text() for p in targets],['1 c4','2 d4','3 e4'])
            self.assertEqual(batch.package_manifest(package),state)

    def test_edited_second_page_blocks_the_whole_optional_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder=root/'diag';folder.mkdir();package=root/'package'
            products,state,first,second,main,manifest=old_package(package)
            first_before=first.read_bytes();second.write_text('my second page')
            report=generated(folder,'song',['1 f4'])
            publications,deletions,updated,status,detail,targets=batch.prepare_blueprints(report,folder,'song',package,products)
            self.assertEqual(status,'blocked');self.assertIn('preserved',detail)
            self.assertEqual((publications,deletions,targets),([],[],[]));self.assertEqual(updated,products)
            self.assertEqual(first.read_bytes(),first_before);self.assertEqual(second.read_text(),'my second page')

    def test_owned_stale_split_is_removed_with_its_manifest_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder=root/'diag';folder.mkdir();package=root/'package'
            products,state,first,second,main,manifest=old_package(package)
            report=generated(folder,'song',['1 f4'])
            publications,deletions,updated,status,detail,targets=batch.prepare_blueprints(report,folder,'song',package,products)
            self.assertEqual(deletions,[second]);self.assertNotIn('blueprint/song.part02.mml',updated)
            state['entries']['song.vgm']['published']=updated
            batch.publish_bundle(publications,manifest,state,folder,deletions=deletions)
            self.assertFalse(second.exists());self.assertEqual(first.read_text(),'1 f4')
            self.assertEqual(batch.package_manifest(package)['entries']['song.vgm']['published'],updated)
            self.assertEqual(main.read_bytes(),b'old VGM')

    def test_deletion_is_rolled_back_with_all_replacements_and_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder=root/'diag';folder.mkdir();package=root/'package'
            products,state,first,second,main,manifest=old_package(package)
            before={p:p.read_bytes() for p in (first,second,main,manifest)}
            report=generated(folder,'song',['1 f4'])
            publications,deletions,updated,*_=batch.prepare_blueprints(report,folder,'song',package,products)
            main_source=folder/'new.vgm';main_source.write_bytes(b'new VGM')
            publications.insert(0,(main_source,main));state['entries']['song.vgm']['published']=updated
            replace=batch.os.replace;failed=[False]
            def fail_manifest(source,target):
                if Path(target)==manifest and not failed[0]:
                    failed[0]=True;raise OSError('authored manifest replacement failure')
                return replace(source,target)
            with patch('batch_vgm_to_mgs.os.replace',side_effect=fail_manifest):
                with self.assertRaisesRegex(OSError,'manifest replacement'):
                    batch.publish_bundle(publications,manifest,state,folder,deletions=deletions)
            self.assertTrue(failed[0])
            for p,data in before.items():self.assertEqual(p.read_bytes(),data)

    def test_invalid_second_page_never_partially_publishes(self):
        for kind in ('foreign','digest','duplicate','missing','name'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);folder=root/'diag';folder.mkdir();package=root/'package'
                products,_,first,second,_,_=old_package(package)
                before=(first.read_bytes(),second.read_bytes());report=generated(folder,'song',['1 f4','2 g4'])
                records=report['blueprint']['files']
                if kind=='foreign':
                    foreign=root/'song.part02.mml';foreign.write_text('external');records[1].update(path=str(foreign),sha256=batch.file_digest(foreign))
                elif kind=='digest':records[1]['sha256']='bad digest'
                elif kind=='duplicate':records[1]=dict(records[0])
                elif kind=='missing':Path(records[1]['path']).unlink()
                else:
                    wrong=folder/'blueprint'/'other.part02.mml';wrong.write_text('2 g4');records[1].update(path=str(wrong),sha256=batch.file_digest(wrong))
                self.assertEqual(batch.blueprint_products(report,folder,'song'),())
                publications,deletions,updated,status,_,targets=batch.prepare_blueprints(report,folder,'song',package,products)
                self.assertEqual(status,'blocked');self.assertEqual((publications,deletions,targets),([],[],[]))
                self.assertEqual(updated,products);self.assertEqual((first.read_bytes(),second.read_bytes()),before)

    def test_malformed_optional_report_cannot_abort_the_main_publication(self):
        for value in (None, 'invalid', []):
            with self.subTest(value=value),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);folder=root/'diag';folder.mkdir();package=root/'package';package.mkdir()
                publications,deletions,updated,status,_,targets=batch.prepare_blueprints(
                    dict(blueprint=value),folder,'song',package,{'tracks/song.vgm':'old'})
                self.assertEqual(status,'blocked')
                self.assertEqual((publications,deletions,targets),([],[],[]))
                self.assertEqual(updated,{'tracks/song.vgm':'old'})

    def test_declared_page_count_mismatch_cannot_publish_a_subset(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder=root/'diag';folder.mkdir();package=root/'package';package.mkdir()
            report=generated(folder,'song',['1 c4','2 d4']);report['blueprint']['file_count']=3
            self.assertEqual(batch.blueprint_products(report,folder,'song'),())
            publications,deletions,updated,status,_,targets=batch.prepare_blueprints(report,folder,'song',package,{})
            self.assertEqual(status,'blocked');self.assertEqual((publications,deletions,targets),([],[],[]))


class ExportBlueprintBundleTests(unittest.TestCase):
    def fake_vgm_worker(self,version,pages):
        def run(command,**kwargs):
            folder=Path(command[command.index('--_worker')+1]);stem=Path(command[2]).stem
            report=generated(folder,stem,pages)
            data=('new VGM '+version).encode();target=folder/(stem+'.reconstructed.vgm');target.write_bytes(data)
            report.update(status='success',vgm_bytes=len(data),units=1,controls=1)
            batch.save_json(folder/'report.json',report)
            return subprocess.CompletedProcess(command,0,b'',b'')
        return run

    def vgm_args(self,source,out):return export_vgm.parser().parse_args([str(source),'--outdir',str(out)])

    def test_recursive_vgm_publishes_all_pages_and_preserves_edits_without_blocking_main(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);inputs=root/'in';source_file(inputs);out=root/'out'
            args=self.vgm_args(inputs,out)
            with patch('export_vgm.subprocess.run',side_effect=self.fake_vgm_worker('1',['1 c4','2 d4'])):
                rows=export_vgm.run_export(args)
            package=out/'site/game';first=package/'blueprint/song.mml';second=package/'blueprint/song.part02.mml'
            self.assertEqual(rows[0]['blueprint_files'],['site/game/blueprint/song.mml','site/game/blueprint/song.part02.mml'])
            self.assertEqual((first.read_text(),second.read_text()),('1 c4','2 d4'))
            second.write_text('my second page')
            with patch('export_vgm.subprocess.run',side_effect=self.fake_vgm_worker('2',['1 f4'])):
                rows=export_vgm.run_export(args)
            self.assertEqual(rows[0]['status'],'success');self.assertEqual(rows[0]['blueprint_status'],'blocked')
            self.assertEqual(first.read_text(),'1 c4');self.assertEqual(second.read_text(),'my second page')
            self.assertEqual((package/'tracks/song.vgm').read_bytes(),b'new VGM 2')
            second.write_text('2 d4')
            with patch('export_vgm.subprocess.run',side_effect=self.fake_vgm_worker('3',['1 f4'])):
                rows=export_vgm.run_export(args)
            self.assertEqual(rows[0]['blueprint_status'],'success');self.assertFalse(second.exists())
            self.assertEqual(first.read_text(),'1 f4')
            entry=batch.package_manifest(package)['entries']['song.vgm']
            self.assertNotIn('blueprint/song.part02.mml',entry['published'])

    def test_mgs_success_can_publish_all_pages_to_recursive_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);inputs=root/'in';source_file(inputs);out=root/'out'
            def run(command,**kwargs):
                if '--outdir' in command:
                    folder=Path(command[command.index('--outdir')+1]);stem=Path(command[2]).stem
                    (folder/(stem+'.mml')).write_text('1 c4')
                    batch.save_json(folder/(stem+'.conversion.json'),generated(folder,stem,['1 c4','2 d4']))
                else:Path(command[2]).write_bytes(b'MGS')
                return subprocess.CompletedProcess(command,0,b'',b'')
            with patch('batch_vgm_to_mgs.shutil.which',return_value='fake-mgsc'),patch('batch_vgm_to_mgs.subprocess.run',side_effect=run):
                rows=batch.run_batch(inputs,out,keyon=False)
            package=out/'site/game'
            self.assertEqual(rows[0]['status'],'success')
            self.assertEqual(rows[0]['blueprint_files'],['site/game/blueprint/song.mml','site/game/blueprint/song.part02.mml'])
            self.assertEqual((package/'blueprint/song.part02.mml').read_text(),'2 d4')
            self.assertEqual((package/'tracks/song.mgs').read_bytes(),b'MGS')
            self.assertEqual(set(batch.package_manifest(package)['entries']['song.vgm']['published']),
                {'tracks/song.mml','tracks/song.mgs','blueprint/song.mml','blueprint/song.part02.mml'})


if __name__=='__main__':unittest.main()
