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


class HDF5PluginWithFileStoreBase(HDF5Plugin, FileStoreHDF5IterativeWrite):
    pass


class HDF5PluginWithFileStoreProsilica(HDF5PluginWithFileStoreBase):
    """Add this as a component to detectors that write HDF5s."""

    def warmup(self):
        """
        This is vendored from ophyd (https://github.com/bluesky/ophyd/blob/master/ophyd/areadetector/plugins.py)
        to fix the non-existent "Internal" trigger mode that is hard-coded there.
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

    def describe(self):
        description = super().describe()
        key = self.parent._image_name

        if not description:
            description[key] = self.parent.make_data_key()

        color_mode = self.parent.cam.color_mode.get(as_string=True)
        if color_mode == "Mono":
            # description[key]["shape"] = (
            #     self.parent.cam.num_images.get(),
            #     self.array_size.height.get(),
            #     self.array_size.width.get(),
            # )
            pass

        elif color_mode in ["RGB1", "Bayer"]:
            description[key]["shape"] = [self.parent.cam.num_images.get(), *self.array_size.get()]
        else:
            raise RuntimeError("Should never be here")

        cam_dtype = self.parent.cam.data_type.get(as_string=True)
        type_map = {"Int8": "|i1", "UInt8": "|u1", "UInt16": "<u2", "Float32": "<f4", "Float64": "<f8"}
        if cam_dtype in type_map:
            description[key].setdefault("dtype_str", type_map[cam_dtype])

        return description


class StandardProsilica(SingleTriggerV33, ProsilicaDetectorV33):
    image = Cpt(ImagePlugin, "ARR:")
    stats = Cpt(StatsPluginV33, "STAT:")
    roi = Cpt(ROIPlugin, "ROI:")
    proc = Cpt(ProcessPlugin, "PROC:")


# TODO: EPICS Meeting workshop participants, please test and propose fixes
# via a PR. Thanks!
class StandardProsilicaWithTIFF(StandardProsilica):
    tiff = Cpt(
        TIFFPluginWithFileStore,
        suffix="TIFF:",
        root="/",
        write_path_template="/data",
        read_path_template="/tmp/data",
    )


class StandardProsilicaWithHDF5(StandardProsilica):
    hdf5 = Cpt(
        HDF5PluginWithFileStoreProsilica,
        suffix="HDF:",
        root="/",
        write_path_template="/data",
        read_path_template="/tmp/data",
    )


cam = StandardProsilicaWithHDF5("BL01T-DI-CAM-01:", name="cam")
cam.wait_for_connection()
cam.cam.ensure_nonblocking()

warmup_hdf5_plugins([cam])

cam.kind = Kind.hinted
cam.stats.kind = Kind.hinted
cam.stats.total.kind = Kind.hinted
cam.hdf5.kind = Kind.hinted

# The IOC's default is 100, resetting it to 1 to speed up individual counts:
cam.cam.num_images.put(1)
