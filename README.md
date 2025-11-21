# tulio

**a personal AI assistant with privacy-aware RAG and a cute desktop companion**

tulio is a privacy-conscious AI assistant that indexes your local files and provides intelligent, context-aware responses using Claude-- with a cute animated desktop pet that reacts to your interactions! you can ask it about your files, have it organize your directory, ask
it about the weather, etc!

tulio is fully functional but still a wip :) demo coming soon!

### note on privacy!

tulio is NOT totally private! it may send content from your files to Anthropic servers temporarily.
(the same that that happens when you send a prompt into Claude directly). make use of the config.yaml
to protect important files and exclude private information!!

## about

tulio has 4 configurable privacy levels it uses when indexing your files. it retrieves
that info as appropriate when interacting with it. it has 12 different animations corresponding
with different emotions that you are welcome to use or make your own!

## instructions

you'll need an anthropic api key!

   1. git clone https://github.com/n0vendy/tulio.git
   2. cd tulio
   3. pip install -r requirements.txt
   4. put api key in .env
   5. edit config.yaml with privacy and style preferences
   6. optionally create "aboutme.txt" to give tulio additional info about you
   7. the system prompt is also edited in claude_client.py, so edit that as you see fit!
      you'll probably want to remove my name, "mira", haha.

   run with python main.py --pet, or without the --pet if you don't want the desktop pet!

## useful commands
- `/help` - show available commands
- `/stats` - indexing statistics  
- `/db` - show database contents
- `/cleanup` - remove excluded files from database
- `/index` - manually trigger indexing
- `/pet` - toggle desktop pet

## known bugs
- sometimes reindexes files even if no changes are made
- will get caught in a thinking loop if asked to open a url

## thank u for checking it out!

**--n0vendy**
