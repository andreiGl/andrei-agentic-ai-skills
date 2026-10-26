"""Focused navigation contract: synthetic DB only, intercept every app URL."""
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import urlsplit,parse_qs
import importlib.util,os,sqlite3,tempfile,unittest
SOURCE=Path(os.environ.get('UPNOTE_TEST_SERVER', str(Path(__file__).resolve().parents[2]/'mcp-servers/upnote-mcp/server.py'))).resolve()
spec=importlib.util.spec_from_file_location('open_candidate',SOURCE);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
class OpenNavigation(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'synthetic.sqlite3'
  with sqlite3.connect(self.db) as c:
   c.executescript("CREATE TABLE notes(id,title,trashed,deleted); CREATE TABLE notebooks(id,title,parent,deleted); CREATE TABLE lists(id,content); CREATE TABLE tags(title,deleted); INSERT INTO notes VALUES('n','Disposable',0,0); INSERT INTO notebooks VALUES('b','Test',NULL,0); INSERT INTO lists VALUES('notebooks_b','[\"n\"]'); INSERT INTO tags VALUES('test tag',0);")
  def connect():
   c=sqlite3.connect('file:'+str(self.db)+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c
  s._connect=connect;self.links=[];s._open_link=lambda url,background=True:self.links.append((url,background))
 def tearDown(self):self.tmp.cleanup()
 def route(self,i):return urlsplit(self.links[i][0]).path,parse_qs(urlsplit(self.links[i][0]).query)
 def test_note_after_restore_resets_notebook_before_foreground_open(self):
  with sqlite3.connect(self.db) as c:c.execute('UPDATE notes SET trashed=1');c.execute('UPDATE notes SET trashed=0')
  self.assertTrue(s.open_in_upnote(note_id='n')['sent']);self.assertEqual(self.route(0),('/openNotebook',{'notebookId':['b']}));self.assertEqual(self.route(1),('/openNote',{'noteId':['n']}));self.assertEqual([x[1] for x in self.links],[True,False])
 def test_unfiled_note_and_trash_use_matching_reset_view(self):
  with sqlite3.connect(self.db) as c:c.execute('DELETE FROM lists')
  s.open_in_upnote(note_id='n');self.assertEqual(self.route(0),('/view',{'mode':['all_notes']}));self.links.clear()
  with sqlite3.connect(self.db) as c:c.execute('UPDATE notes SET trashed=1')
  self.assertTrue(s.open_in_upnote(note_id='n')['showing']['trashed']);self.assertEqual(self.route(0),('/view',{'mode':['trash']}))
 def test_invalid_targets_dispatch_nothing(self):
  for args in [{},{'note_id':'missing'},{'notebook':'missing'},{'tag':'missing'},{'note_id':'n','search':'x'}]:
   with self.assertRaises(s.ToolError):s.open_in_upnote(**args)
  self.assertEqual(self.links,[])
 def test_other_modes_retain_single_foreground_dispatch_and_encode_values(self):
  for args,path,key,value in [({'notebook':'b'},'/openNotebook','notebookId','b'),({'tag':'test tag'},'/tag/view','tag','test tag'),({'search':'a&b #c'},'/view','query','a&b #c')]:
   self.links.clear();s.open_in_upnote(**args);self.assertEqual(len(self.links),1);self.assertEqual(self.route(0)[0],path);self.assertEqual(self.route(0)[1][key],[value]);self.assertFalse(self.links[0][1])
 def test_dispatch_failure_does_not_claim_success_or_continue(self):
  def fail(url,background=True):raise RuntimeError('dispatch refused')
  s._open_link=fail
  with self.assertRaisesRegex(RuntimeError,'dispatch refused'):s.open_in_upnote(note_id='n')
if __name__=='__main__':unittest.main(verbosity=2)
