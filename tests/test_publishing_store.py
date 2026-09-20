import unittest
from app.publishing.store import Store, Conflict
from support_publishing import Fixture


class StoreTests(unittest.TestCase):
    def setUp(self): self.f=Fixture()
    def tearDown(self): self.f.close()
    def test_restart_and_idempotency(self):
        run=self.f.run()
        self.assertEqual(self.f.run()["id"],run["id"])
        reopened=Store(self.f.root/"publishing.db")
        self.assertEqual(reopened.run(run["id"])["source_name"],"My recording.wav")
        with self.assertRaises(Conflict): reopened.create_run({},"test-key-123","different")
    def test_atomic_review_revision(self):
        run=self.f.run()
        self.f.store.change(run["id"],{"revision":2},revision=1)
        with self.assertRaises(Conflict): self.f.store.change(run["id"],{"revision":3},revision=1)
    def test_state_one_use_and_expiration(self):
        self.f.store.save_state("state",{"profile":"one"})
        self.assertEqual(self.f.store.consume_state("state"),{"profile":"one"})
        with self.assertRaises(ValueError): self.f.store.consume_state("state")
        self.f.store.save_state("old",{})
        with self.f.store.db() as db: db.execute("UPDATE oauth_states SET expires=0")
        with self.assertRaises(ValueError): self.f.store.consume_state("old")
