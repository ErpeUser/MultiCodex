import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from multicodex.jobs import JobRunner, JobBusy
from multicodex.settings import SettingsStore

class JobsTests(unittest.TestCase):
    def test_duplicate_job_is_not_enqueued(self):
        jobs=JobRunner();self.addCleanup(jobs.close)
        release=threading.Event();self.addCleanup(release.set)
        jobs.submit('one',lambda:release.wait(1))
        with self.assertRaises(JobBusy): jobs.submit('one',lambda:None)
        release.set()

    def test_work_runs_off_calling_thread_and_result_is_drained(self):
        main=threading.get_ident();jobs=JobRunner();self.addCleanup(jobs.close)
        jobs.submit('one',threading.get_ident)
        result=[]
        for _ in range(100):
            result=jobs.drain()
            if result: break
            time.sleep(.005)
        self.assertEqual(len(result),1)
        self.assertNotEqual(result[0].value,main)
        self.assertIsNone(result[0].error)
        self.assertEqual(jobs.pending,0)

    def test_exception_is_returned_without_being_printed(self):
        jobs=JobRunner();self.addCleanup(jobs.close)
        def broken(): raise ValueError('synthetic exception')
        jobs.submit('one',broken)
        result=[]
        for _ in range(100):
            result=jobs.drain()
            if result:break
            time.sleep(.005)
        self.assertIsInstance(result[0].error,ValueError)

    def test_closed_runner_refuses_new_work(self):
        jobs=JobRunner();jobs.close()
        with self.assertRaises(JobBusy): jobs.submit('x',lambda:None)

class SettingsTests(unittest.TestCase):
    def test_appearance_survives_restart(self):
        with tempfile.TemporaryDirectory() as d:
            settings=SettingsStore(Path(d))
            settings.save_theme('light')
            self.assertEqual(SettingsStore(Path(d)).load()['theme'],'light')

    def test_arbitrary_fields_and_bad_theme_not_written(self):
        with tempfile.TemporaryDirectory() as d:
            settings=SettingsStore(Path(d))
            with self.assertRaises(ValueError):settings.save_theme('bad')
            self.assertFalse(settings.path.exists())

    def test_corrupt_settings_are_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            settings=SettingsStore(Path(d));settings.path.write_text('corrupt')
            self.assertEqual(settings.load()['theme'],'dark')
            self.assertTrue(settings.problem)
            with self.assertRaises(ValueError):settings.save_theme('light')
            self.assertEqual(settings.path.read_text(),'corrupt')
