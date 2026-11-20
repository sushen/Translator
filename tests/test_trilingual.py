import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from types import SimpleNamespace
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pymupdf
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtWidgets import QApplication
from app.document.trilingual_project import (new_project,save_project,load_project,revise,
    fingerprint,apply_proposal,split_unit,join_units,export_project)
from app.processing.trilingual_worker import TrilingualWorker,prepare,generate,bind_sources
from app.gui.trilingual_window import TrilingualWindow


def project():
    p=new_project('english.pdf','french.pdf')
    p['french_pages']=[dict(physical_page=3,text='Texte français. Autre paragraphe.')]
    p['units']=[dict(id='unit-a',english='English paragraph one.',english_pages=[5],french=[dict(page=3,text='Texte français.')],
                    bangla='সম্পাদিত বাংলা অনুবাদ।',alignment_status='reviewed',alignment_note='Reviewed.',status='translated',history=[]),
                dict(id='unit-b',english='English paragraph two.',english_pages=[6],french=[],bangla='',alignment_status='unmatched',history=[])]
    return p


class TrilingualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_roundtrip_history_and_split_join_do_not_discard_text(self):
        p=project();u=p['units'][0];old=u['bangla'];revise(u,{'bangla':'নতুন বাংলা।'})
        self.assertEqual(u['history'][0]['unit']['bangla'],old)
        split_unit(p,0,8);self.assertEqual(p['units'][0]['bangla'],'নতুন বাংলা।');self.assertEqual(p['units'][1]['bangla'],'')
        join_units(p,0);self.assertEqual(len(p['units']),2);self.assertIn('paragraph one.',p['units'][0]['english'])
        self.assertTrue(p['archived_units'])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'book.json';save_project(p,path);self.assertEqual(load_project(path),p)

    def test_proposals_are_explicit_and_stale_proposals_are_rejected(self):
        p=project();u=p['units'][0];original=u['bangla']
        proposal=dict(kind='refine',basis=fingerprint(u),bangla='উন্নত বাংলা।')
        u['proposal']=proposal;self.assertEqual(u['bangla'],original)
        u['english']='Corrected source'
        with self.assertRaisesRegex(ValueError,'changed'):apply_proposal(p,u,'refine')
        u['proposal']=dict(proposal,basis=fingerprint(u));apply_proposal(p,u,'refine')
        self.assertEqual(u['bangla'],'উন্নত বাংলা।');self.assertEqual(u['history'][-1]['unit']['bangla'],original)

    def test_alignment_cannot_claim_unverified_french_as_matched(self):
        p=project();u=p['units'][0]
        worker=TrilingualWorker(p,'align',ids=[u['id']],request=lambda *args:dict(french=[dict(page=3,text='Invented')],alignment_status='matched'))
        worker.run();out=worker.project['units'][0]
        self.assertEqual(out['french'],u['french']);self.assertEqual(out['proposal']['alignment_status'],'uncertain')
        apply_proposal(worker.project,out,'align');self.assertEqual(out['alignment_status'],'uncertain')

    def test_missing_counterpart_remains_distinct_from_an_unverified_match(self):
        p=project();u=p['units'][0]
        worker=TrilingualWorker(p,'align',ids=[u['id']],request=lambda *args:dict(french=[],alignment_status='no_counterpart',alignment_note='No corresponding passage in the prepared evidence.'))
        worker.run();out=worker.project['units'][0]
        self.assertEqual(out['french'],u['french'])
        self.assertEqual(out['proposal']['alignment_status'],'no_counterpart')
        apply_proposal(worker.project,out,'align')
        self.assertEqual(out['alignment_status'],'no_counterpart');self.assertEqual(out['french'],[])

    def test_cancel_retains_completed_proposal_and_manual_edits(self):
        p=project()
        def request(config,kind,unit,context):
            self.assertEqual(unit['bangla'],p['units'][0]['bangla']);self.assertEqual(unit['french'],p['units'][0]['french'])
            worker.requestInterruption();return dict(bangla='প্রস্তাবিত বাংলা।')
        worker=TrilingualWorker(p,'retranslate',ids=['unit-a','unit-b'],request=request)
        # requestInterruption only applies to running QThreads, so exercise the real thread.
        outcome=[];worker.outcome.connect(lambda p,m:outcome.append((p,m)))
        self.wait_worker(worker)
        self.assertTrue(outcome);self.assertEqual(worker.project['units'][0]['bangla'],p['units'][0]['bangla'])
        self.assertTrue(worker.project['units'][0]['proposal']);self.assertNotIn('proposal',worker.project['units'][1])

    def wait_worker(self,worker):
        loop=QEventLoop();worker.finished.connect(loop.quit);timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(loop.quit);timer.start(15000)
        worker.start();loop.exec()
        self.assertFalse(worker.isRunning(),'Worker did not finish in 15 seconds')
        self.app.processEvents()

    def test_prepare_arbitrary_ranges_heading_and_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            en=Path(folder)/'en.pdf';fr=Path(folder)/'fr.pdf'
            for path in (en,fr):
                with pymupdf.open() as pdf:
                    page=pdf.new_page();page.insert_text((70,70),'PREFACE');page.insert_text((70,120),'MAIN OPENING');page.insert_text((70,170),'Body paragraph.')
                    pdf.new_page().insert_text((70,70),'Second source paragraph.');pdf.save(path)
            p=new_project();options=dict(english_pdf=str(en),french_pdf=str(fr),english_start=1,english_end=2,french_start=1,french_end=2,
                                        first_heading='MAIN OPENING',force_french_ocr=False,batch_id='test')
            prepare(p,options,lambda *args:None,lambda:False)
            self.assertEqual(len(p['units']),2);self.assertNotIn('PREFACE',p['units'][0]['english'])
            p['units'][0]['bangla']='মানব সম্পাদনা।';p['french_pages'][0]['text']='Corrected OCR'
            with patch('app.processing.trilingual_worker.ocr_page',side_effect=AssertionError('Existing corrected OCR must not be rerun')):
                prepare(p,dict(options,force_french_ocr=True,batch_id='retry'),lambda *args:None,lambda:False)
            self.assertEqual(len(p['units']),2);self.assertEqual(p['units'][0]['bangla'],'মানব সম্পাদনা।');self.assertEqual(p['french_pages'][0]['text'],'Corrected OCR')

    def test_export_uses_current_edits_safe_html_and_readable_pdf(self):
        p=project();p['units'][0]['english']='Corrected <script>alert(1)</script> reference.'
        p['units'][0]['bangla']='বর্তমান সম্পাদিত বাংলা।'
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'reading.pdf';export_project(p,path)
            html=path.with_suffix('.html').read_text(encoding='utf-8')
            self.assertIn('বর্তমান সম্পাদিত বাংলা।',html);self.assertIn('&lt;script&gt;',html);self.assertNotIn('<script>',html)
            self.assertLess(html.index('Texte français.'),html.index('Corrected &lt;script&gt;'))
            self.assertLess(html.index('Corrected &lt;script&gt;'),html.index('বর্তমান সম্পাদিত বাংলা।'))
            with pymupdf.open(path) as pdf:
                text=' '.join(page.get_text() for page in pdf)
                self.assertIn('End of aligned reading batch.',text);self.assertIn('End of alignment notes.',text)
                self.assertEqual(text.count('unit-a'),2)
            with self.assertRaises(ValueError):export_project(p,path)
            export_project(p,Path(folder)/'independent.html',True)
            self.assertFalse((Path(folder)/'independent.pdf').exists())

    def test_gui_navigation_edit_accept_reject_and_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            window=TrilingualWindow(lambda:{'mock':True},project=project(),output_dir=folder)
            window.bangla.setPlainText('আমার বাংলা সম্পাদনা।');window.table.setCurrentCell(1,0)
            self.assertEqual(window.project['units'][0]['bangla'],'আমার বাংলা সম্পাদনা।')
            window.table.setCurrentCell(0,0);window.mode.setCurrentIndex(1)
            window.run_ai('refine',True)
            worker=window.worker;loop=QEventLoop();worker.finished.connect(loop.quit);QTimer.singleShot(15000,loop.quit);loop.exec();self.app.processEvents()
            self.assertFalse(worker.isRunning());self.assertIn('proposal',window.project['units'][0]);self.assertEqual(window.bangla.toPlainText(),'আমার বাংলা সম্পাদনা।')
            window.accept_button.click();self.assertIn('পরীক্ষামূলক',window.bangla.toPlainText())
            self.assertTrue(window.project['units'][0]['history'])
            self.assertTrue(window.recovery_path.exists())
            window.project['units'][0]['proposal']=dict(kind='refine',basis=fingerprint(window.project['units'][0]),bangla='পুরনো প্রস্তাব।')
            window.show_proposal();window.bangla.setPlainText('আরও সম্পাদনা।')
            self.assertNotIn('proposal',window.project['units'][0]);self.assertFalse(window.accept_button.isEnabled())
            window.capture();self.assertEqual(window.project['units'][0]['bangla'],'আরও সম্পাদনা।')
            window.dirty=False;window.close()

    def test_improvement_request_contains_both_sources_and_current_bangla(self):
        p=project();u=p['units'][0];client=MagicMock()
        client.__enter__.return_value=client
        client.chat.completions.create.return_value=SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content='{"bangla":"উন্নত বাংলা।","reasons":"test","ambiguities":"none"}'))])
        factory=MagicMock(return_value=client)
        with patch.dict('sys.modules',{'openai':SimpleNamespace(OpenAI=factory)}),patch('app.translation.http_client.verified_http_client',return_value=MagicMock()):
            result=generate(dict(key='test-only',model='mock',instructions='Keep terminology'),'refine',u,p)
        self.assertEqual(result['bangla'],'উন্নত বাংলা।')
        payload=json.loads(client.chat.completions.create.call_args.kwargs['messages'][1]['content'])
        self.assertEqual(payload['english'],u['english']);self.assertEqual(payload['french'],u['french']);self.assertEqual(payload['current_bangla'],u['bangla'])
        self.assertEqual(factory.call_args.kwargs['max_retries'],0)

    def test_partial_failure_preserves_completed_proposals_and_original_text(self):
        p=project();calls=[];errors=[]
        def request(config,kind,unit,context):
            calls.append(unit['id'])
            if len(calls)==2:raise RuntimeError('sensitive-provider-error')
            return dict(bangla='প্রস্তাবিত বাংলা।')
        worker=TrilingualWorker(p,'retranslate',ids=['unit-a','unit-b'],request=request);worker.problem.connect(errors.append);worker.run()
        self.assertEqual(worker.project['units'][0]['bangla'],p['units'][0]['bangla'])
        self.assertIn('proposal',worker.project['units'][0]);self.assertNotIn('proposal',worker.project['units'][1])
        self.assertTrue(errors);self.assertNotIn('sensitive-provider-error',errors[0])

    def test_native_import_save_reopen_and_original_pilot_preservation(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);pilot=folder/'pilot.json'
            old=project();old.pop('format');old['schema_version']=1;pilot.write_text(json.dumps(old),encoding='utf-8');before=pilot.read_bytes()
            window=TrilingualWindow(lambda:{'mock':True},output_dir=folder)
            window.open_path(pilot);self.assertIsNone(window.project_path)
            native=folder/'native.json';window.project_path=str(native);window.bangla.setPlainText('সংরক্ষিত সম্পাদনা।');window.save()
            window.open_path(native);self.assertEqual(window.project_path,str(native));self.assertEqual(window.bangla.toPlainText(),'সংরক্ষিত সম্পাদনা।')
            self.assertEqual(pilot.read_bytes(),before);window.dirty=False;window.close()

    def test_moved_identical_sources_can_be_relinked_but_other_book_cannot(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);old=folder/'old.pdf';new=folder/'new.pdf';other=folder/'other.pdf'
            old.write_bytes(b'identical source');new.write_bytes(old.read_bytes());other.write_bytes(b'another book')
            p=project();p.update(english_pdf=str(old),french_pdf=str(old))
            bind_sources(p,dict(english_pdf=str(new),french_pdf=str(new)))
            self.assertEqual(p['english_pdf'],str(new))
            with self.assertRaises(ValueError):bind_sources(p,dict(english_pdf=str(other),french_pdf=str(new)))

    def test_gui_export_captures_latest_manual_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            window=TrilingualWindow(lambda:{'mock':True},project=project(),output_dir=folder)
            window.bangla.setPlainText('রপ্তানির সর্বশেষ সম্পাদনা।');target=Path(folder)/'edited.html'
            with patch('app.gui.trilingual_window.QFileDialog.getSaveFileName',return_value=(str(target),'')):
                window.export_html()
            loop=QEventLoop();window.worker.finished.connect(loop.quit);QTimer.singleShot(15000,loop.quit);loop.exec();self.app.processEvents()
            self.assertFalse(window.worker.isRunning());self.assertIn('রপ্তানির সর্বশেষ সম্পাদনা।',target.read_text(encoding='utf-8'))
            window.dirty=False;window.close()

    def test_resume_does_not_request_an_existing_valid_proposal_again(self):
        p=project();u=p['units'][0]
        u['proposal']=dict(kind='refine',basis=fingerprint(u),bangla='সংরক্ষিত প্রস্তাব।')
        worker=TrilingualWorker(p,'refine',ids=[u['id']],request=lambda *args:(_ for _ in ()).throw(AssertionError('Paid request repeated')))
        errors=[];worker.problem.connect(errors.append);worker.run()
        self.assertFalse(errors);self.assertEqual(worker.project['units'][0]['proposal']['bangla'],'সংরক্ষিত প্রস্তাব।')


if __name__=='__main__':unittest.main()
