{-# LANGUAGE LambdaCase #-}
-- Runs every fetched body through the exact parser brockman uses
-- (Text.Feed.Import.parseFeedSource) and brockman's feedToItems item rules.
-- stdin: one file path per line
-- stdout: path \t kind \t items \t brockmanItems \t strictItems \t links
--   kind: atom | rss | rss1 | xml (parsed, but not a known feed) | none (parse failed)
--   brockmanItems: items brockman's feedToItems would keep
--   strictItems: items with a non-empty title AND non-empty link
--   links: space-separated links of the strict items (used to spot same-content duplicates)
import Control.Exception (SomeException, evaluate, try)
import qualified Data.ByteString.Lazy as BL
import Data.Maybe (listToMaybe, mapMaybe)
import qualified Data.Text as T
import System.IO
import qualified Text.Atom.Feed as Atom
import Text.Feed.Import (parseFeedSource)
import Text.Feed.Query (feedItems)
import qualified Text.Feed.Types as Feed
import qualified Text.RSS.Syntax as RSS
import qualified Text.RSS1.Syntax as RSS1

-- (title, link) exactly as brockman's Brockman.Feed.feedToItems extracts them
fromItem :: Feed.Item -> Maybe (T.Text, T.Text)
fromItem = \case
  Feed.AtomItem entry ->
    let title = T.pack $ Atom.txtToString $ Atom.entryTitle entry
        link = Atom.linkHref <$> listToMaybe (Atom.entryLinks entry)
     in (,) title <$> link
  Feed.RSSItem item ->
    let title = maybe (maybe (T.pack "untitled") id (RSS.rssItemDescription item)) id (RSS.rssItemTitle item)
     in (,) title <$> RSS.rssItemLink item
  Feed.RSS1Item item -> Just (RSS1.itemTitle item, RSS1.itemLink item)
  _ -> Nothing

strict :: Feed.Item -> Bool
strict item = case item of
  Feed.RSSItem i -> nonEmpty (RSS.rssItemTitle i) && nonEmpty (RSS.rssItemLink i)
  _ -> case fromItem item of
    Just (t, l) -> ok t && ok l
    Nothing -> False
  where
    ok = not . T.null . T.strip
    nonEmpty = maybe False ok

check :: FilePath -> IO String
check path = do
  r <- try $ do
    body <- BL.readFile path
    let feed = parseFeedSource body
        kind = case feed of
          Nothing -> "none"
          Just (Feed.AtomFeed _) -> "atom"
          Just (Feed.RSSFeed _) -> "rss"
          Just (Feed.RSS1Feed _) -> "rss1"
          Just (Feed.XMLFeed _) -> "xml"
        items = maybe [] feedItems feed
        n = length items
        b = length (mapMaybe fromItem items)
        good = filter strict items
        links = unwords [T.unpack (T.strip l) | Just (_, l) <- map fromItem good, T.all (`notElem` "\t\n\r ") (T.strip l)]
        s = length good
    _ <- evaluate (n + b + s + length links) -- force inside try
    return (kind, n, b, s, links)
  return $ case r of
    Left e -> path ++ "\terror\t0\t0\t0\t\t" ++ take 200 (filter (`notElem` "\t\n") (show (e :: SomeException)))
    Right (k, n, b, s, l) -> path ++ "\t" ++ k ++ "\t" ++ show n ++ "\t" ++ show b ++ "\t" ++ show s ++ "\t" ++ l

main :: IO ()
main = do
  hSetBuffering stdout LineBuffering
  paths <- lines <$> getContents
  mapM_ (\p -> check p >>= putStrLn) paths
