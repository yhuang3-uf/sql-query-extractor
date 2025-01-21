## Message Passing between Extractor and Parser
Strings will be passed from the extractor to the parser. SQL queries most often contain blanks that need to be filled in. Therefore, the following have special meanings when in a strings being passed from the extractor to the parser:
`$01` to `$99` - Blanks
`$$` - A literal dollar sign
