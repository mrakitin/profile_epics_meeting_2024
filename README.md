# IPython profile for the Bluesky Workshop at the EPICS Meeting (Fall 2024).

## Details

**Date/time:** September 20, 2024, 9:00-10:20 am

**Link:**  https://conference.sns.gov/event/448/page/3139-workgroups-and-training

The IPython profile with the ophyd/bluesky configuration to work with the [EPICS containers](https://github.com/epics-containers/example-services) started with [these changes](https://github.com/epics-containers/example-services/compare/main...mrakitin:epics-containers-example-services:debug-gateway-image?expand=1) to the main repository.

## Setup

The demo will be perfomed on Linux (x86_64).

### Terminal tab 1:

```bash
git clone https://github.com/mrakitin/epics-containers-example-services.git
git checkout debug-gateway-image
ln -sv $PWD/environment.sh /tmp/
. /tmp/environment.sh  # also repeat this step in the terminal tab 2
docker compose up
```

### Terminal tab 2:

Clone this repo:

```bash
mkdir -p ~/.ipython/
cd ~/.ipython/
git clone https://github.com/mrakitin/profile_epics_meeting_2024.git
cd profile_epics_meeting_2024/
```

Create a conda environment:

```bash
conda create -n epics-meeting-bluesky python=3.11 ipython -c conda-forge -y
conda activate epics-meeting-bluesky
pip install -r requirements.txt
```

Start IPython with the clonned profile:

```bash
. /tmp/environment.sh
ipython --profile=epics_meeting_2024
```

Run bluesky's `count` plan:

```python
RE(bp.count([cam], num=3))
```

Retrieve a databroker header for a previous run and get the data:

```python
hdr = db[-1]
hdr.table()
imgs = np.array(list(hdr.data("cam_image")))
```

Example output:

```python
In [1]: RE(bp.count([cam], num=3))


Transient Scan ID: 3     Time: 2024-09-19 23:37:18
Persistent Unique Scan ID: '919fb48f-f37d-45bd-8e1a-5065250155e6'
New stream: 'primary'
+-----------+------------+-----------------+
|   seq_num |       time | cam_stats_total |
+-----------+------------+-----------------+
|         1 | 23:37:19.1 |         -524288 |
|         2 | 23:37:19.9 |         -524288 |
|         3 | 23:37:20.7 |         -524288 |
+-----------+------------+-----------------+
generator count ['919fb48f'] (scan num: 3)



Out[1]: ('919fb48f-f37d-45bd-8e1a-5065250155e6',)

In [2]: hdr = db[-1]

In [3]: hdr.table()
Out[3]:
         cam_stats_total                          time
seq_num
1              -524288.0 2024-09-20 03:37:19.174373150
2              -524288.0 2024-09-20 03:37:19.997307301
3              -524288.0 2024-09-20 03:37:20.764054775

In [4]: imgs = np.array(list(hdr.data("cam_image")))

In [5]: imgs
Out[5]:
array([[[[-11, -10,  -9, ..., -14, -13, -12],
         [-10,  -9,  -8, ..., -13, -12, -11],
         [ -9,  -8,  -7, ..., -12, -11, -10],
         ...,
         [-14, -13, -12, ..., -17, -16, -15],
         [-13, -12, -11, ..., -16, -15, -14],
         [-12, -11, -10, ..., -15, -14, -13]]],


       [[[-10,  -9,  -8, ..., -13, -12, -11],
         [ -9,  -8,  -7, ..., -12, -11, -10],
         [ -8,  -7,  -6, ..., -11, -10,  -9],
         ...,
         [-13, -12, -11, ..., -16, -15, -14],
         [-12, -11, -10, ..., -15, -14, -13],
         [-11, -10,  -9, ..., -14, -13, -12]]],


       [[[ -9,  -8,  -7, ..., -12, -11, -10],
         [ -8,  -7,  -6, ..., -11, -10,  -9],
         [ -7,  -6,  -5, ..., -10,  -9,  -8],
         ...,
         [-12, -11, -10, ..., -15, -14, -13],
         [-11, -10,  -9, ..., -14, -13, -12],
         [-10,  -9,  -8, ..., -13, -12, -11]]]], dtype=int8)

In [6]: imgs.shape
Out[6]: (3, 1, 1024, 1024)

In [7]: plt.imshow(imgs[0][0])
Out[7]: <matplotlib.image.AxesImage at 0x7fae2005b950>

```
