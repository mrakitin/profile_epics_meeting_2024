import time as ttime  # tea time
from collections import OrderedDict
from datetime import datetime
from pathlib import PurePath
from types import SimpleNamespace

import dask
from area_detector_handlers.handlers import H5PY_KEYERROR_IOERROR_MSG, AreaDetectorHDF5Handler
from bluesky.plan_stubs import close_run, open_run, pause, stage, trigger_and_read, unstage
from nslsii.ad33 import SingleTriggerV33, StatsPluginV33
from ophyd import AreaDetector
from ophyd import Component as Cpt
from ophyd import (
    DetectorBase,
    Device,
    EpicsSignal,
    EpicsSignalRO,
    ImagePlugin,
    Kind,
    ProcessPlugin,
    ProsilicaDetector,
    ProsilicaDetectorCam,
    ROIPlugin,
    Signal,
    SingleTrigger,
    StatsPlugin,
    TransformPlugin,
)
from ophyd.areadetector.base import ADComponent, EpicsSignalWithRBV
from ophyd.areadetector.cam import AreaDetectorCam
from ophyd.areadetector.filestore_mixins import (
    FileStoreBase,
    FileStoreHDF5IterativeWrite,
    FileStoreIterativeWrite,
    FileStoreTIFFIterativeWrite,
    new_short_uid,
)
from ophyd.areadetector.plugins import HDF5Plugin_V34 as HDF5Plugin
from ophyd.areadetector.plugins import TIFFPlugin_V34 as TIFFPlugin


class ProsilicaDetectorCamV33(ProsilicaDetectorCam):
    wait_for_plugins = Cpt(EpicsSignal, "WaitForPlugins", string=True, kind="config")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs["wait_for_plugins"] = "Yes"

    def ensure_nonblocking(self):
        self.stage_sigs["wait_for_plugins"] = "Yes"
        for c in self.parent.component_names:
            cpt = getattr(self.parent, c)
            if cpt is self:
                continue
            if hasattr(cpt, "ensure_nonblocking"):
                cpt.ensure_nonblocking()


class ProsilicaDetectorV33(ProsilicaDetector):
    cam = Cpt(ProsilicaDetectorCamV33, "DET:")


class TIFFPluginWithFileStore(TIFFPlugin, FileStoreTIFFIterativeWrite):
    """Add this as a component to detectors that write TIFFs."""

    pass


class HDF5PluginWithFileStoreBase(HDF5Plugin, FileStoreHDF5IterativeWrite): ...


class HDF5PluginWithFileStoreBaseRGB(HDF5PluginWithFileStoreBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filestore_spec = "AD_HDF5_RGB"


class HDF5PluginWithFileStoreProsilica(HDF5PluginWithFileStoreBase):
    """Add this as a component to detectors that write HDF5s."""

    def warmup(self):
        """
        This is vendored from ophyd (https://github.com/bluesky/ophyd/blob/master/ophyd/areadetector/plugins.py)
        to fix the non-existent "Internal" trigger mode that is hard-coded there:

            In [13]: cam6.stage()
            An exception has occurred, use '%tb verbose' to see the full traceback.
            UnprimedPlugin: The plugin hdf5 on the area detector with name cam6 has not been primed.

            See /home/xf08bm/bluesky-files/log/bluesky/bluesky.log for the full traceback.

            In [14]: cam6.hdf5.warmup()
            An exception has occurred, use '%tb verbose' to see the full traceback.
            ValueError: invalid literal for int() with base 0: b'Internal'

            See /home/xf08bm/bluesky-files/log/bluesky/bluesky.log for the full traceback.
        """
        self.enable.set(1).wait()
        sigs = OrderedDict(
            [
                (self.parent.cam.array_callbacks, 1),
                (self.parent.cam.image_mode, "Single"),
                (
                    self.parent.cam.trigger_mode,
                    "Fixed Rate",
                ),  # updated here "Internal" -> "Fixed Rate"
                # just in case tha acquisition time is set very long...
                (self.parent.cam.acquire_time, 1),
                (self.parent.cam.acquire_period, 1),
                (self.parent.cam.acquire, 1),
            ]
        )

        original_vals = {sig: sig.get() for sig in sigs}

        for sig, val in sigs.items():
            ttime.sleep(0.1)  # abundance of caution
            sig.set(val).wait()

        ttime.sleep(2)  # wait for acquisition

        for sig, val in reversed(list(original_vals.items())):
            ttime.sleep(0.1)
            sig.set(val).wait()

    def get_frames_per_point(self):
        if not self.parent.is_flying:
            return self.parent.cam.num_images.get()
        else:
            return 1


class TIFFPluginEnsuredOff(TIFFPlugin):
    """Add this as a component to detectors that do not write TIFFs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs.update([("auto_save", "No")])


class StandardProsilica(SingleTriggerV33, ProsilicaDetectorV33):
    image = Cpt(ImagePlugin, "ARR:")
    stats = Cpt(StatsPluginV33, "STAT:")
    # stats2 = Cpt(StatsPluginV33, 'Stats2:')
    # stats3 = Cpt(StatsPluginV33, 'Stats3:')
    # stats4 = Cpt(StatsPluginV33, 'Stats4:')
    # stats5 = Cpt(StatsPluginV33, 'Stats5:')
    # trans1 = Cpt(TransformPlugin, 'Trans1:')
    roi = Cpt(ROIPlugin, "ROI:")
    # roi2 = Cpt(ROIPlugin, 'ROI2:')
    # roi3 = Cpt(ROIPlugin, 'ROI3:')
    # roi4 = Cpt(ROIPlugin, 'ROI4:')
    proc1 = Cpt(ProcessPlugin, "PROC:")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._is_flying = False

    @property
    def is_flying(self):
        return self._is_flying

    @is_flying.setter
    def is_flying(self, is_flying):
        self._is_flying = is_flying


class CustomTIFFPluginWithFileStore(TIFFPluginWithFileStore):
    def get_frames_per_point(self):
        if not self.parent.is_flying:
            return self.parent.cam.num_images.get()
        else:
            return 1


class StandardProsilicaWithTIFF(StandardProsilica):
    tiff = Cpt(
        CustomTIFFPluginWithFileStore,
        suffix="TIFF1:",
        write_path_template="/data",
        root="/",
    )


class StandardProsilicaWithHDF5(StandardProsilica):
    hdf5 = Cpt(
        HDF5PluginWithFileStoreProsilica,
        suffix="HDF:",
        write_path_template="/data",
        root="/",
    )


class CamWithHDF5(StandardProsilica):
    hdf5 = Cpt(
        HDF5PluginWithFileStoreBaseRGB,
        suffix="HDF:",
        write_path_template="/data",
        root="/",
    )


class ADURLHDF5Handler(AreaDetectorHDF5Handler):
    """
    Modification of the Area Detector handler HDF5 for RGB data.
    """

    def __call__(self, point_number):
        # Don't read out the dataset until it is requested for the first time.
        if self._dataset is None:
            try:
                self._dataset = dask.array.from_array(self._file[self._key])
                self._dataset = self._dataset.sum(axis=-1)
            except KeyError as error:
                raise IOError(H5PY_KEYERROR_IOERROR_MSG) from error

        return super().__call__(point_number)


db.reg.register_handler("AD_HDF5_RGB", ADURLHDF5Handler, overwrite=True)


cam = CamWithHDF5("BL01T-DI-CAM-01:", name="cam")
cam.wait_for_connection()
warmup_hdf5_plugins([cam])

cam.cam.ensure_nonblocking()

cam.kind = Kind.hinted
cam.stats.kind = Kind.hinted
cam.stats.total.kind = Kind.hinted
cam.hdf5.kind = Kind.hinted

# The IOC's default is 100, resetting it to 1 to speed up individual counts:
cam.cam.num_images.put(1)
