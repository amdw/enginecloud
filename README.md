# DIY Chess Engine Cloud

## Introduction

This project contains a set of scripts and instructions to help run modern
[chess engines](https://en.wikipedia.org/wiki/Chess_engine) in virtual machines
(VMs) on [Google Compute Engine](https://cloud.google.com/compute), and access
them over the Internet from a chess GUI as if they were running on your local
computer.

(Full disclosure: I work for Google Cloud, but this is a personal project which
is not reviewed or endorsed by Google. The techniques illustrated in this
repository could easily be adapted to other cloud providers.)

This is a sort of "do-it-yourself" version of "Cloud Engine" products such as
[ChessBase Engine
Cloud](https://en.chessbase.com/post/tutorial-how-does-the-engine-cloud-work) or
[Chessify](https://chessify.me/). The advantages of a DIY approach are:

* It can cost less, especially for short periods of use, because you only pay
  the cost of running the VMs on the cloud provider. Modern cloud providers
  usually provide very fine-grained billing, even down to the second, so you
  only pay for exactly what you use.
* You get full control over the software and (virtual) hardware: you can choose
  a location for the VMs close to you to minimise latency, what VM type you use
  (how many CPU cores, what type of CPU etc), what version of the chess software
  you run etc.
* It is an opportunity to learn more about cloud infrastructure, chess software,
  and potentially other technical topics.

The disadvantages compared to a paid Cloud Engine product are:

* A greater degree of technical expertise is required. This project is designed
  to reduce that somewhat, but you still need to make a number of decisions that
  require a degree of understanding, and install and use software on your
  computer that is normally only used by developers.
* You won't get the kind of customer support you would get from a dedicated
  provider.
* The pricing model of cloud providers is more complex, and once you start using
  billable resources, stopping typically requires explicit action on your part
  (such as deleting the VM). This leads to a greater risk you will make a
  mistake (such as forgetting to delete a VM after you have finished with it)
  and spend more than you intended. See disclaimer below.

## Disclaimer

This is Apache-licensed software and thus comes with **no warranty** of any
kind. It is **your responsibility** to understand [how Google Compute Engine
pricing works](https://cloud.google.com/compute/all-pricing) before you start,
to understand what these scripts do before running them, to make sure you stop
consuming billable resources after you no longer need them, and to use cost
management tools like
[budgets](https://cloud.google.com/billing/docs/how-to/budgets) to avoid
accidentally spending more than you intended.

## Why?

Computer chess engines are indispensable tools for learning about the game. For
example, analysing your own games with an engine is a fascinating and sobering
experience, as they show you many possibilities missed by one or both players!

Computer hardware and chess software have advanced to the point where even a
mobile phone, or an engine compiled to JavaScript and run in a web browser such
as the Stockfish version used in [the Lichess analysis
tool](https://lichess.org/analysis), is far stronger than any human. For casual
users, for example wanting to run a quick check on their games to find out where
the key turning points were, these are quite sufficient.

However, there is still a big gap in strength today between an engine like that
and an engine run optimally on the most powerful hardware currently available.
If run natively on a high-spec modern server, an engine can make use of multiple
processor cores to analyse much deeper much quicker.

Chess is not such a trivial game that you can just run any old engine on any
position for a few seconds and get a perfect answer. There is a reason why
professional chess players rely on these more powerful engine setups for serious
analysis: anyone who has had the experience of seeing a slower engine change its
mind (for example after thinking for a while, or after you have played a few
moves down its main line) will have a sense of what that reason is. There is
also a reason why the [Top Computer Engine Championship
(TCEC)](https://tcec-chess.com/) uses high-end servers; any browser-based chess
engine entered into that competition would be utterly crushed.

Of course, better performance can be obtained by running an engine natively
using multiple threads on a modern laptop or desktop, but very few people have
as much computing power in their homes as the most powerful VMs you can get from
a modern cloud provider (and that's before you even think about [running an
engine on a cluster](https://mattplayschess.com/stockfish-cluster/) of multiple
VMs!).

Modern consumer hardware is very different from server hardware, especially with
devices like laptops that place some degree of emphasis on power efficiency
rather than raw performance. Chess engine developers often understandably tend
to place more emphasis on optimising the performance of their software on the
latter than the former, since that is where they primarily compete.

Another important trend is the emergence of chess engines based on ["deep neural
networks"](https://en.wikipedia.org/wiki/Deep_learning). DeepMind's
[AlphaZero](https://en.wikipedia.org/wiki/AlphaZero) caused a major stir in
2017-18 with its style of play in defeating Stockfish in a test match. [Leela
Chess Zero](https://lczero.org/) soon followed, trying to build a similar
architecture in an open source project, and is now regularly used by chess
professionals and cited as an inspiration for their ideas.

These engines can only run at optimal performance using [GPU
hardware](https://en.wikipedia.org/wiki/Graphics_processing_unit) far more
powerful than anything found in most normal home computers: GPU manufacturers
now produce models specifically aimed at servers running in data centres, for
use cases like deep neural networks. Few people will be able and willing to make
the serious investment of buying such hardware just for chess analysis, but
renting it for short periods from a cloud provider is much more economical.

## How does this project work?

As noted in the introduction, several "Cloud Engine" services have sprung up to
offer hosted chess engines to paying customers. I don't have any special insight
into how these are implemented, but if you know how modern chess software works,
it is not hard to imagine how it might be done. Virtually all modern engines
support a text-based protocol called
[UCI](https://en.wikipedia.org/wiki/Universal_Chess_Interface), which forms a
standard interface between chess engines and chess GUIs. These days, thanks to
UCI, virtually any engine can be used with any chess GUI.

If a chess GUI can speak UCI to an engine running on the local machine, why
can't it communicate in exactly the same way over a network with an engine
running on a remote machine? The GUI wouldn't even have to know the network was
involved: it could invoke a local program which would connect to the remote
machine using a protocol like [SSH](https://en.wikipedia.org/wiki/Secure_Shell),
and forward the UCI messages in both directions. From the GUI's perspective, the
whole setup would look exactly the same as a local engine.

All we need to do is (a) create a suitable VM, (b) install our engine of choice
on it, and then (c) configure our chess GUI with a command which invokes the
engine via SSH.

Step (a) is pretty straightforward with a modern cloud provider (on Google
Cloud, it's mainly a case of running [a `gcloud`
command](https://cloud.google.com/sdk/gcloud/reference/compute/instances/create)
with the right parameters).

Step (b) depends on the engine: it can be simple if the engine we want has a
pre-built binary available which we can just download, but it can be more
complex if we need to build the engine from source.

Step (c) really ought to be very simple: just run [`gcloud compute
ssh`](https://cloud.google.com/sdk/gcloud/reference/compute/ssh) with a
`--command` flag to invoke the engine. Unfortunately however, many chess GUIs
don't allow you to provide additional command line parameters to an engine, and
won't invoke a shell script either: they expect a native binary that can be
invoked without arguments. My workaround for this involves generating and
compiling a small [Go](https://go.dev/) program with the right `gcloud` command
hard-coded into it. It's not elegant, but it works.

This doesn't add up to a polished product like the professional Cloud engines do
-- you have to put in a lot more effort -- but if you do everything right, you
will get basically the same thing much cheaper, especially if you only want to
use the engine for a few hours per month. And you may learn something and have
fun in the process!

## Instructions

### Prerequisites

* A computer with a Unix-like environment (e.g. MacOS or Linux), to run the
  commands. The techniques in this repository should be possible to use from
  Windows as well, but I have no personal interest in doing that.
* A Google Cloud account (see [this guide](https://cloud.google.com/docs/get-started))
* A Google Cloud project with the [Google Compute Engine
  API](https://console.cloud.google.com/compute) enabled
* You will need the following software installed:
  * A text editor of your choice
  * The `bash` shell
  * [The Go toolchain](https://go.dev/) (running `go version` should spit out
    some relatively recent version)
  * [The gcloud CLI](https://cloud.google.com/sdk/gcloud) - scripts in this
    repository assume you have `gcloud` on your `PATH` and have run `gcloud
    init`
  * A [chess GUI which supports UCI
    engines](https://www.chessprogramming.org/UCI#GUIs). All my testing was done
    using [HIARCS Chess Explorer](https://www.hiarcs.com/chess-explorer.html),
    but there are plenty of free and open source options.
* Sufficient [Google Compute Engine
  quota](https://cloud.google.com/compute/quotas) to run the types of VM you
  want. The quota you get with a free trial account or a newly set up account
  should be sufficient for basic experiments with Stockfish, but for machine
  types with more CPU cores or GPUs, you will need to obtain additional quota.

All shell commands are run from the root of this repository unless otherwise
stated.

Chess software is still advancing rapidly, and so are the features offered by
cloud providers. It's entirely possible you will need to change the scripts in
order to get the best results (e.g. upgrade to a newer engine version), or to
make things work at all. Pull requests are welcome!

### Stockfish

[Stockfish](https://stockfishchess.org/) is a wonderful open source chess
engine, which is one of the strongest in the world. Many people will have used
it already in some form.

First create a settings file:

```bash
cp stockfish/settings_template.sh stockfish/settings.sh
```

and then edit `stockfish/settings.sh`. Check all the environment variables set
there, and set the ones which are blank. At a minimum, you need to specify:

* `GCP_PROJECT`: the project ID of the Google Cloud project where you want to
  create the VM. (You can find this under "Project info" in the [Google Cloud
  Dashboard](https://console.cloud.google.com/home/dashboard) when you have the
  correct project selected in the drop-down at the top. Alternatively, run
  `gcloud projects list`.)
* `GCP_ZONE`: the [GCE
  zone](https://cloud.google.com/compute/docs/regions-zones) where you want to
  create your VM. There are various considerations here: all else being equal,
  you want to choose a zone as close to you as possible to minimise network
  latency, but zones vary in terms of cost (e.g. see [VM instance
  pricing](https://cloud.google.com/compute/vm-instance-pricing)) and
  availability of certain machine types.
* `GCP_MACHINE_TYPE`: the machine type used to create the VM. This will
  determine the type and number of CPU cores your Stockfish VM has. For a full
  list of machine types, you can run `gcloud compute machine-types list`;
  alternatively you can choose your desired values from the drop-downs in the
  [instance creation web
  UI](https://console.cloud.google.com/compute/instancesAdd), then click the
  "Equivalent Command Line" button at the bottom instead of "Create", and see
  what value is used for the `--machine-type` parameter. If you're just trying
  this out to see if it works, you can use `e2-medium`, but if you want decent
  performance, you will need something larger.

You should also check the other environment variables:

* `EC_HOME`: a directory where the project can store binaries and other files.
  By default, `$HOME/enginecloud` will be used. I recommend using a directory
  dedicated to this project, which does not contain any other files you care
  about, as several scripts will write files here.
* `STOCKFISH_VERSION`: the version of Stockfish that will be downloaded and
  used.
* `GCP_IMAGE_PROJECT` and `GCP_IMAGE_FAMILY`: these determine [the OS
  image](https://cloud.google.com/compute/docs/images) used to create your VM.
* `GCP_INSTANCE_NAME`: the name of the VM instance that will be created for
  Stockfish inside your project.

Once you are happy, you can run `stockfish/start.sh`. This will generate and
compile a Go program at `$EC_HOME/run_stockfish` to connect to your VM and run
Stockfish, and create your VM instance. **(Creating a VM will start to consume
billable resources.)**

Once `start.sh` completes successfully, you can test the VM by running the
`run_stockfish` program from the shell; if you see the Stockfish welcome
message, you should be good to go. Sometimes you have to try it a few times
before it succeeds, as it will take the VM a few seconds to download and unpack
Stockfish after it starts up.

Once this works, open your chess GUI of choice, and configure it with a new
engine. When it asks you for the engine binary, choose the `run_stockfish`
program. You should be able to use this just like any other engine -- except the
engine is running in the cloud. If you get this far, congratulations: you have a
working cloud engine!

(If the `run_stockfish` program worked from the command line but doesn't work
from your chess GUI -- for example if it complains it's not a working UCI engine
or that the engine died unexpectedly -- one tip is to make sure you don't have
any firewall software running that is blocking the chess GUI from reaching the
GCE APIs or your VM.)

It's very important for performance to set the number of threads in the UCI
engine settings. You should use a value *at least* equal to the number of CPU
cores your VM has, otherwise you are wasting cores. Play with various values and
see what gets you the best performance; most chess UIs have a way to show you
the calculation speed of the engine while it is analysing.

Once you have finished with the engine, you should run `stockfish/stop.sh` to
delete the VM, so you are no longer charged for it. Alternatively, you can do it
manually via the Google Compute Engine console or the `gcloud` CLI.

You can run `stockfish/check.sh` at any time to confirm what VM instances you
have running in your specified project.

## Leela Chess Zero

[Leela Chess Zero](https://lczero.org/) is a chess engine based on deep neural
networks. As mentioned in the introduction, it aims to use similar techniques to
AlphaZero.

It's another incredible open source project, but it's not as accessible as
Stockfish. At the time of writing, Leela Chess Zero is much harder to get
working, for a few reasons:

* There is no pre-built binary for Linux: we have to build it from source. (The
  way we do this is based on [the LC0
  README](https://github.com/LeelaChessZero/lc0) and [this
  guide](https://lczero.org/dev/wiki/google-cloud-guide-lc0/), among various
  other sources.)
* To get optimal performance, we need to use a [machine type that has at least
  one GPU](https://cloud.google.com/compute/docs/gpus). We have to choose the
  GPU type we want, and our choice will restrict the [GCE zones we can
  use](https://cloud.google.com/compute/docs/gpus/gpu-regions-zones). GPUs also
  require [special quota](https://cloud.google.com/compute/quotas#gpu_quota).
* Using GPUs also requires us to download and install various libraries and
  drivers, including but not limited to
  [these](https://cloud.google.com/compute/docs/gpus/install-drivers-gpu). Some
  of the software we need is quite large to download, and not all of it is open
  source.
* Even once we have built Leela Chess Zero, we still have to choose a neural
  network to run it with, which is [a non-trivial
  decision](https://lczero.org/play/networks/bestnets/) in itself.

*This section is a work in progress: instructions and scripts for Leela Chess
Zero will be added later.*

## Acknowledgements and sources

First, I must salute the developers who write these amazing chess engines, make
them available to the world as open source software, and continue to find ways
to make them stronger and stronger. I've been working with chess engines for
long enough to remember a time when the best open source engines were vastly
weaker than the proprietary ones; the fact that open source engines are now
among today's very strongest is a huge triumph for open source software and a
credit to the people who work on them.

I'm not the first person to do a project like this; I took heavy inspiration
from [MattPlaysChess's Cloud Engine blog
series](https://mattplayschess.com/series/cloud-engines/).

The [TCEC
wiki](https://wiki.chessdom.org/TCEC_Season_Further_information#TCEC_Hardware)
was a helpful source of information on the kind of hardware used for top-level
engine play.

## License

All software in this repository is available under the open source Apache 2.0
license: see [LICENSE.txt](LICENSE.txt). Pull requests are welcome.
