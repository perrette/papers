# Tests of the specification

The test cases of the Python version for each rule of the specification,
by file and section. They say what is on disk and on the command line
after each command, so a second implementation can be checked against
the same cases. Files `tests/test_spec_<file>.py` hold the tests written
for the specification. A section marked free has none.

## library.md

### Layout

- tests/test_library_folder.py::LibraryFolderTest::test_origin_in_library_folder
- tests/test_library_folder.py::LibraryFolderTest::test_distinct_in_library_folder
- tests/test_library_folder.py::LibraryFolderTest::test_move_from_bibtex_folder
- tests/test_library_folder.py::LibraryFolderTest::test_no_move_over_existing_file
- tests/test_library_folder.py::LibraryFolderTest::test_undo_across_the_move
- tests/test_library_folder.py::LibraryFolderTest::test_other_library_left_alone
- tests/test_spec_library.py::TestLayout::test_papers_folder_of_the_library_directory
- tests/test_spec_library.py::TestLayout::test_no_move_with_dry_run
- tests/test_spec_library.py::TestFindingTheLibrary::test_bibtex_without_library

### `.papers/.gitignore`

- tests/test_history.py::TestPlaces::test_no_trace_before_a_change
- tests/test_history.py::TestPlaces::test_gitignore
- tests/test_history.py::TestPlaces::test_gitignore_without_a_save_of_the_configuration

### `.papers/distinct.json`

- see `bibtex.md` section 9.4.

### `.papers/files.json`, `.papers/origin/`

- see `history.md` section 10 and `exchange.md`.

### Format

- tests/test_spec_library.py::TestConfigurationFormat::test_written_format
- tests/test_spec_library.py::TestConfigurationFormat::test_read_as_utf8
- tests/test_safe_writes.py::TestWriteAtomic::test_write
- tests/test_safe_writes.py::TestWriteAtomic::test_symlink

### Keys

- tests/test_spec_library.py::TestConfigurationKeys::test_format_keys
- tests/test_spec_library.py::TestConfigurationKeys::test_other_keys
- tests/test_config_v3.py::TestConfigCommand::test_types
- tests/test_config_unit.py::TestLibraryId::test_machine_settings_not_read_from_a_library

### Which keys papers writes

- tests/test_config_v3.py::TestResolution::test_save_keeps_inherited_settings_out
- tests/test_config_v3.py::TestResolution::test_unset
- tests/test_config_v3.py::TestResolution::test_v2_local_config
- tests/test_config_v3.py::TestInit::test_init
- tests/test_config_v3.py::TestInit::test_init_options
- tests/test_config_v3.py::TestInit::test_init_machine_defaults
- tests/test_config_v3.py::TestConfigCommand::test_explicit_values_saved
- tests/test_config_v3.py::TestConfigCommand::test_get_set_unset
- tests/test_config_v3.py::TestConfigCommand::test_prune
- tests/test_config_v3.py::TestFormatVersion::test_written
- tests/test_config_v3.py::TestFormatVersion::test_earlier_v3_settings
- tests/test_config_unit.py::TestLibraryId::test_unknown_keys_kept
- tests/test_config_unit.py::TestLibraryId::test_machine_settings_not_read_from_a_library
- tests/test_spec_library.py::TestWrittenKeys::test_paths_written_as_null
- tests/test_spec_library.py::TestWrittenKeys::test_init_writes_pool_and_paths
- tests/test_spec_library.py::TestWrittenKeys::test_prune_removes_the_settings_of_papers_2

### Reading

- tests/test_config_more.py::TestJson::test_invalid_version
- tests/test_config_more.py::TestConfig::test_wrong_type
- tests/test_config_v3.py::TestFormatVersion::test_newer_version
- tests/test_config_v3.py::TestFormatVersion::test_newer_version_command
- tests/test_config_v3.py::TestFormatVersion::test_v3_ignores_v2_settings
- tests/test_config_v3.py::TestFormatVersion::test_earlier_v3_settings
- tests/test_pools_onetime.py::TestPoolSettingAsList::test_one_path
- tests/test_pools_onetime.py::TestPoolSettingAsList::test_several_paths
- tests/test_config_unit.py::TestLibraryId::test_invalid_id_ignored
- tests/test_config_v3.py::TestConfigCommand::test_errors
- tests/test_library_cmds.py::TestConfigCmd::test_bad_value
- tests/test_spec_library.py::TestConfigurationFormat::test_read_as_utf8
- tests/test_spec_library.py::TestReading::test_unknown_pool_name
- tests/test_spec_library.py::TestReading::test_pools_item_that_is_a_path
- tests/test_spec_library.py::TestReading::test_null_is_unset

### The `id` field

- tests/test_config_unit.py::TestLibraryId::test_created_once_and_kept
- tests/test_config_unit.py::TestLibraryId::test_invalid_id_ignored
- tests/test_config_unit.py::TestLibraryId::test_only_the_id_is_written
- tests/test_config_unit.py::TestLibraryId::test_written_to_papers_config_json
- tests/test_history.py::TestPlaces::test_no_trace_before_a_change
- tests/test_spec_library.py::TestIdField::test_id_is_a_uuid4
- tests/test_spec_library.py::TestIdField::test_no_id_with_dry_run
- tests/test_spec_library.py::TestFindingTheLibrary::test_bibtex_without_library

### Relative paths

- tests/test_config_unit.py::TestPathsOfSettings::test_home_in_bibtex_and_filesdir
- tests/test_config_v3.py::TestConfigCommand::test_paths_normalized
- tests/test_config_v3.py::TestConfigCommand::test_paths_are_absolute
- tests/test_config_v3.py::TestInit::test_init_dir
- tests/test_config_v3.py::TestInit::test_init_paths_relative_to_current_directory
- tests/test_paths.py::TestLocalConfigSubfolder::test_save_from_another_directory
- tests/test_config_more.py::TestConfig::test_relpath_failure_keeps_the_path
- tests/test_library_cmds.py::TestConfigCmd::test_filesdir_that_does_not_exist
- tests/test_spec_library.py::TestRelativePaths::test_symbolic_links
- tests/test_spec_library.py::TestRelativePaths::test_absolute_stays_absolute
- tests/test_spec_library.py::TestRelativePaths::test_pool_resolved_against_the_library

### Library configuration of papers 2: `.papersconfig.json`

- tests/test_config_location.py::TestFindLibraryConfig::test_both_names_from_a_subdirectory
- tests/test_config_location.py::TestFindLibraryConfig::test_both_files_are_an_error
- tests/test_config_location.py::TestV2Library::test_found
- tests/test_config_location.py::TestV2Library::test_moved_on_save
- tests/test_config_location.py::TestV2Library::test_dry_run_moves_nothing
- tests/test_config_location.py::TestV2Library::test_both_files
- tests/test_config_location.py::TestV2Library::test_migrate
- tests/test_config_location.py::TestInit::test_init_in_a_v2_library
- tests/test_config_v3.py::TestResolution::test_v2_local_config
- tests/test_config_v3.py::TestFormatVersion::test_v3_ignores_v2_settings
- tests/test_library_unit.py::TestLegacyConfig::test_v2_dot_papers_read_in_place
- tests/test_library_unit.py::TestLegacyConfig::test_v2_dot_papers_saved_in_place
- tests/test_pools.py::TestResolution::test_v2_project_library

### Global configuration of papers 2: `papersconfig.json`

- tests/test_config_v3.py::TestMigrateV2Global::test_still_used_before_migration
- tests/test_config_v3.py::TestMigrateV2Global::test_migrate
- tests/test_config_v3.py::TestMigrateV2Global::test_migrate_relative
- tests/test_config_v3.py::TestMigrateV2Global::test_existing_library_config_is_kept
- tests/test_config_v3.py::TestMigrateV2Global::test_other_default_library_is_kept
- tests/test_config_v3.py::TestMigrateV2Global::test_install_global_is_an_error
- tests/test_config_more.py::TestConfig::test_v2_global_configuration

### Global configuration of papers 2: `papersconfig.json`

- tests/test_library_unit.py::TestLegacyConfig::test_global_config_is_moved
- tests/test_library_unit.py::TestLegacyConfig::test_both_exist

### Location

- tests/test_spec_library.py::TestMachineConfiguration::test_location (Linux)

### Format

- tests/test_config_v3.py::TestFormatVersion::test_written
- tests/test_config_v3.py::TestFormatVersion::test_newer_version
- tests/test_config_more.py::TestMachineConfig::test_unreadable
- tests/test_config_more.py::TestMachineConfig::test_wrong_type
- tests/test_config_more.py::TestMachineConfig::test_right_types
- tests/test_config_more.py::TestMachineConfig::test_pool_names_of_earlier_v3
- tests/test_config_more.py::TestMachineConfig::test_pool_names_kept_on_save
- tests/test_pools_onetime.py::TestPoolSettingAsList::test_global
- tests/test_spec_library.py::TestMachineConfiguration::test_written_format

### Format

- tests/test_config_v3.py::TestDefaultLibrary::test_config_global_default
- tests/test_config_v3.py::TestDefaultLibrary::test_init_global
- tests/test_config_more.py::TestMachineConfig::test_default_library
- tests/test_config_unit.py::TestPathsOfSettings::test_relative_to_the_global_configuration
- tests/test_library_cmds.py::TestConfigCmd::test_global_path_relative_to_current_directory
- tests/test_library_cmds.py::TestConfigCmd::test_global_default_takes_one_path
- tests/test_spec_library.py::TestMachineConfiguration::test_default_written_with_home
- tests/test_spec_library.py::TestMachineConfiguration::test_history_dir_written_absolute

### Table

- tests/test_spec_library.py::TestSettings::test_table
- tests/test_spec_library.py::TestSettings::test_where
- tests/test_library_cmds.py::TestConfigCmd::test_machine_settings
- tests/test_files_mode.py::TestSetting::test_default_is_move

### Precedence

- tests/test_config_v3.py::TestResolution::test_order
- tests/test_config_v3.py::TestDefaultLibrary::test_builtin_default
- tests/test_config_v3.py::TestConfigCommand::test_global
- tests/test_config_v3.py::TestConfigCommand::test_global_library_only
- tests/test_config_v3.py::TestFormatOptions::test_no_key_unknown_strict
- tests/test_files_mode.py::TestSetting::test_machine_then_library
- tests/test_files_mode.py::TestModes::test_options_override_setting
- tests/test_pools.py::TestResolution::test_no_pool_setting
- tests/test_pools.py::TestShallow::test_add_places_files_in_pool
- tests/test_spec_library.py::TestSettings::test_command_line_first

### Finding the library of a command

- tests/test_config_v3.py::TestDirectoryOption::test_C
- tests/test_config_v3.py::TestDirectoryOption::test_C_missing
- tests/test_cli_unit.py::TestMain::test_C_attached_form
- tests/test_cli_unit.py::TestMain::test_C_combined
- tests/test_cli_unit.py::TestMain::test_C_not_a_directory
- tests/test_config_location.py::TestFindLibraryConfig::test_none
- tests/test_config_location.py::TestFindLibraryConfig::test_both_names_from_a_subdirectory
- tests/test_config_location.py::TestFindLibraryConfig::test_both_files_are_an_error
- tests/test_config_v3.py::TestMigrateV2Global::test_still_used_before_migration
- tests/test_config_v3.py::TestDefaultLibrary::test_outside_library
- tests/test_config_v3.py::TestDefaultLibrary::test_no_library
- tests/test_config_v3.py::TestDefaultLibrary::test_library_takes_precedence
- tests/test_spec_library.py::TestFindingTheLibrary::test_first_library_upwards
- tests/test_spec_library.py::TestFindingTheLibrary::test_root_never_searched
- tests/test_spec_library.py::TestFindingTheLibrary::test_bibtex_of_the_library_from_elsewhere
- tests/test_spec_library.py::TestFindingTheLibrary::test_bibtex_without_library

### Finding the library of a command

- tests/test_config_v3.py::TestInit::test_init
- tests/test_config_v3.py::TestInit::test_init_existing
- tests/test_config_v3.py::TestInit::test_init_dir
- tests/test_config_v3.py::TestInit::test_init_paths_relative_to_current_directory
- tests/test_library_cmds.py::TestOtherCommands::test_init_dir_not_left_behind
- tests/test_library_cmds.py::TestOtherCommands::test_init_in_a_library
- tests/test_install.py::TestLocalInstall::test_install_defaults_no_preexisting_bibtex
- tests/test_install.py::TestLocalInstall::test_install_defaults_preexisting_bibtex
- tests/test_install.py::TestLocalInstall::test_install_defaults_preexisting_pdfs

### The pool setting

- tests/test_config_v3.py::TestInit::test_init_options
- tests/test_config_v3.py::TestInit::test_init_paths_relative_to_current_directory
- tests/test_config_v3.py::TestConfigCommand::test_types
- tests/test_config_v3.py::TestDefaultLibrary::test_init_shallow
- tests/test_pools.py::TestConfigPool::test_pool_path_written_relative
- tests/test_pools_onetime.py::TestSmallFixes::test_config_pool_path_with_home
- tests/test_spec_library.py::TestPoolSetting::test_written_with_home
- tests/test_spec_library.py::TestPoolSetting::test_inside_the_library

### States

- tests/test_config_v3.py::TestFormatVersion::test_v3_ignores_v2_settings
- tests/test_pools.py::TestResolution::test_never_itself
- tests/test_pools.py::TestResolution::test_errors
- tests/test_pools.py::TestConfigPoolSelfContained::test_config_pool_not_the_library_itself
- tests/test_pools.py::TestConfigPoolSelfContained::test_init_pool_must_be_a_library_without_pool
- tests/test_pools.py::TestConfigPoolSelfContained::test_earlier_local_setting_ignored

### States

- tests/test_pools.py::TestConfigPoolSelfContained::test_pool_must_be_a_library_without_pool
- tests/test_pools.py::TestConfigPoolSelfContained::test_init_pool_must_be_a_library_without_pool
- tests/test_pools.py::TestConfigPoolSelfContained::test_configured_pool_that_takes_a_pool
- tests/test_config_v3.py::TestDefaultLibrary::test_config_global_default
- tests/test_pools.py::TestResolution::test_missing_pool_is_a_warning
- tests/test_pools.py::TestResolution::test_missing_library_is_never_created
- tests/test_pools.py::TestResolution::test_push_to_missing_pool
- tests/test_config_location.py::TestInit::test_pool_that_is_not_a_library
- tests/test_spec_library.py::TestRulesOnThePool::test_auto_push_warns

### Files of a shallow library

- tests/test_pools.py::TestShallow::test_add_places_files_in_pool
- tests/test_pools.py::TestShallow::test_file_attach_places_files_in_pool
- tests/test_pools.py::TestShallow::test_file_rename_places_files_in_pool
- tests/test_pools.py::TestConfigPoolSelfContained::test_init_shallow_has_no_files_directory
- tests/test_pools_more.py::TestExchange::test_pool_without_filesdir
- tests/test_pools.py::TestConfigPoolSelfContained::test_refused
- tests/test_pools.py::TestConfigPoolSelfContained::test_becomes_shallow
- tests/test_pools.py::TestConfigPoolSelfContained::test_same_paper_different_content
- tests/test_pools.py::TestConfigPoolSelfContained::test_dry_run
- tests/test_pools.py::TestConfigPoolSelfContained::test_no_terminal
- tests/test_pools.py::TestConfigPoolSelfContained::test_pool_none
- tests/test_pools.py::TestConfigPool::test_pool_none
- tests/test_pools.py::TestConfigPool::test_pool_none_no_terminal
- tests/test_pools.py::TestConfigPool::test_other_pool

### The files setting

- tests/test_files_mode.py::TestSetting::test_ask
- tests/test_files_mode.py::TestSetting::test_ask_answers
- tests/test_files_mode.py::TestSetting::test_invalid
- tests/test_files_mode.py::TestModes::test_move
- tests/test_files_mode.py::TestModes::test_copy_is_hard_link
- tests/test_files_mode.py::TestModes::test_copy_without_hard_link
- tests/test_files_mode.py::TestModes::test_link
- tests/test_files_mode.py::TestModes::test_rename_is_move
- tests/test_files_mode.py::TestAttach::test_attach
- tests/test_files_mode.py::TestOtherLibrary::test_move_falls_back_to_copy
- tests/test_files_mode.py::TestOtherLibrary::test_outside_files_directory_is_moved
- tests/test_files_mode.py::TestOtherLibrary::test_own_files_directory_is_not_other
- tests/test_files_unit.py::TestPolicy::test_download_is_moved
- tests/test_pools.py::TestAdd::test_copy_mode
- tests/test_pools.py::TestAdd::test_move_mode_never_moves_pool_files
- tests/test_pools.py::TestShallow::test_add_same_pdf_move_mode
- tests/test_file_relink.py::TestSearch::test_move
- tests/test_file_relink.py::TestOtherLibrary::test_move_still_copies

### File names

- tests/test_paths.py::TestFlatLayout::test_names
- tests/test_paths.py::TestFlatLayout::test_new_name_keeps_labels
- tests/test_paths.py::TestFlatLayout::test_same_labels
- tests/test_paths.py::TestFlatLayout::test_legacy_directory
- tests/test_paths.py::TestFlatLayout::test_legacy_directory_with_other_files
- tests/test_paths.py::TestRenameInPlace::test_single_file
- tests/test_paths.py::TestRenameInPlace::test_several_files
- tests/test_paths.py::TestMoveSameFile::test_hardlink_is_moved
- tests/test_file_cmd.py::TestSameFileName::test_two_papers_same_name
- tests/test_file_cmd.py::TestSameFileName::test_same_content_is_the_same_file
- tests/test_filename_unit.py::TestSafeFileNames::test_length
- tests/test_filename_unit.py::TestSafeFileNames::test_attachments_fit
- tests/test_config_v3.py::TestMigrateFolders::test_folders
- tests/test_spec_library.py::TestFileNames::test_extension

### Syntax

- tests/test_filename_unit.py::TestPlaceholders::test_unknown_placeholder
- tests/test_file_cmd.py::TestRename::test_unknown_placeholder
- tests/test_spec_library.py::TestTemplateSyntax::test_literal_braces

### Placeholders

- tests/test_spec_library.py::TestPlaceholders::test_authors
- tests/test_spec_library.py::TestPlaceholders::test_missing_fields

### Placeholders

- tests/test_filename_unit.py::TestTitleLength::test_drops_last_words
- tests/test_filename_unit.py::TestTitleLength::test_one_word_left
- tests/test_filename_unit.py::TestTitleLength::test_long_first_word_is_cut
- tests/test_filename_unit.py::TestTitleLength::test_word_num
- tests/test_filename_unit.py::TestTitleLength::test_word_size
- tests/test_filename_unit.py::TestTitleLength::test_separator_counts
- tests/test_filename_unit.py::TestTitleLength::test_template
- tests/test_config_v3.py::TestFormatOptions::test_key_title_length
- tests/test_spec_library.py::TestPlaceholders::test_title_placeholders

### Placeholders

- tests/test_filename_unit.py::TestPlaceholders::test_key
- tests/test_filename_unit.py::TestUnknownKeySanitized::test_unknown_key_from_doi_is_sanitized
- tests/test_path_traversal.py::TestPathSafe::test_separators
- tests/test_path_traversal.py::TestPathSafe::test_fields
- tests/test_spec_library.py::TestPlaceholders::test_missing_fields
- tests/test_spec_library.py::TestPlaceholders::test_doi_placeholders

### Placeholders

- tests/test_filename_unit.py::TestSlugTable::test_unidecode_whatever_the_slugify_backend
- tests/test_spec_library.py::TestPlaceholders::test_slugify
- tests/test_spec_library.py::TestPlaceholders::test_unidecode_version

### Placeholders

- tests/test_filename_unit.py::TestFormatIsUnknown::test_unknown_strict_all_must_be_unknown
- tests/test_filename_unit.py::TestFormatIsUnknown::test_unknown_non_strict_any_is_unknown
- tests/test_config_v3.py::TestFormatOptions::test_key_unknown_template
- tests/test_config_v3.py::TestFormatOptions::test_key_unknown_strict
- tests/test_config_v3.py::TestFormatOptions::test_unknown_strict_default_is_the_setting

### File names

- tests/test_filename_unit.py::TestSafeFileNames::test_windows_characters
- tests/test_filename_unit.py::TestSafeFileNames::test_reserved_names
- tests/test_filename_unit.py::TestSafeFileNames::test_no_journal
- tests/test_filename_unit.py::TestSafeFileNames::test_length
- tests/test_path_traversal.py::TestRename::test_subfolders_still_work

### Keys

- tests/test_bib_fix.py::TestFixEntry::test_auto_key_keeps_a_right_key
- tests/test_bib_fix.py::TestFixEntry::test_auto_key_suffix_is_stable
- tests/test_bib_fix.py::TestFixEntry::test_fix_key
- tests/test_config_v3.py::TestDefaultLibrary::test_outside_library
- tests/test_filename_unit.py::TestSafeFileNames::test_keys_unchanged
- tests/test_spec_library.py::TestTemplateKeys::test_key_not_transformed
- tests/test_spec_bibtex.py::TestKeySuffix::test_empty_template_key

### Path safety

- tests/test_path_traversal.py::TestPathSafe::test_fields
- tests/test_path_traversal.py::TestRename::test_fields_stay_inside
- tests/test_path_traversal.py::TestRename::test_template_outside_is_refused
- tests/test_path_traversal.py::TestRename::test_subfolders_still_work
- tests/test_path_traversal.py::TestAddBibtex::test_add

### File

- tests/test_lock.py::TestLock::test_acquire_release
- tests/test_spec_library.py::TestLockFile::test_content
- tests/test_spec_library.py::TestLockFile::test_no_lock
- tests/test_spec_library.py::TestLockFile::test_dot_papers_created
- tests/test_spec_library.py::TestLayout::test_papers_folder_of_the_library_directory

### Protocol

- tests/test_lock.py::TestLock::test_acquire_release
- tests/test_lock.py::TestLock::test_wait_then_error
- tests/test_lock.py::TestLock::test_released_while_waiting
- tests/test_lock.py::TestLock::test_stale_process_gone
- tests/test_lock.py::TestLock::test_stale_not_refreshed
- tests/test_lock.py::TestLock::test_refreshed_lock_is_not_stale
- tests/test_lock.py::TestLock::test_refresh
- tests/test_lock.py::TestLock::test_take_over_only_the_stale_file
- tests/test_lock.py::TestLock::test_take_over_without_hard_links
- tests/test_lock.py::TestLock::test_take_over
- tests/test_lock.py::TestLock::test_refresh_does_not_rewrite
- tests/test_lock.py::TestLock::test_lost
- tests/test_spec_library.py::TestLockProtocol::test_unreadable_lock_is_being_written
- tests/test_spec_library.py::TestLockProtocol::test_check_recreates_a_removed_lock
- tests/test_spec_library.py::TestLockProtocol::test_check_unreadable_goes_on

### Protocol

- tests/test_lock.py::TestCommands::test_pool_locked_too
- tests/test_lock.py::TestUndoLocksPool::test_undo_waits_for_the_pool
- tests/test_lock.py::TestCommands::test_writing_command_waits

### Protocol

- tests/test_spec_library.py::TestLockProtocol::test_values

### Protocol

- tests/test_lock.py::TestCommands::test_reading_command_does_not_wait
- tests/test_lock.py::TestCommands::test_writing_command_waits

## bibtex.md

### 1. Text encoding and line endings

- tests/test_spec_bibtex.py::TestEncodingAndLineEnds::test_line_ends_read_and_written_as_lf
- tests/test_spec_bibtex.py::TestEncodingAndLineEnds::test_invalid_utf8_stops
- tests/test_unchanged_save.py::TestReadWrite::test_byte_order_mark
- tests/test_spec_bibtex.py::TestEncodingAndLineEnds::test_byte_order_mark_of_an_added_bibtex
- tests/test_spec_bibtex.py::TestEncodingAndLineEnds::test_byte_order_mark_from_the_editor
- tests/test_spec_bibtex.py::TestEncodingAndLineEnds::test_distinct_json_utf8_lf
- tests/test_spec_bibtex.py::TestDistinctFile::test_reading

### 2.1 Blocks

- tests/test_spec_bibtex.py::TestBlocks::test_block_kinds
- tests/test_spec_bibtex.py::TestBlocks::test_keyword_case_delimiters_whitespace
- tests/test_sort_format.py::TestSortFormat::test_sort_format_unchanged

### 2.2 Entries

- tests/test_spec_bibtex.py::TestEntries::test_type_key_field_names
- tests/test_spec_bibtex.py::TestEntries::test_entry_without_fields
- tests/test_spec_bibtex.py::TestEntries::test_values
- tests/test_spec_bibtex.py::TestEntries::test_values_not_decoded
- tests/test_parsing.py::TestFieldNames::test_capitals

### 2.3 `@string` and `@preamble`

- tests/test_spec_bibtex.py::TestStringsAndPreamble::test_references_resolved
- tests/test_spec_bibtex.py::TestStringsAndPreamble::test_later_string_wins
- tests/test_spec_bibtex.py::TestStringsAndPreamble::test_written

### 2.4 Comments

- tests/test_spec_bibtex.py::TestComments::test_explicit_comment_trimmed
- tests/test_spec_bibtex.py::TestComments::test_implicit_comment_one_block
- tests/test_spec_bibtex.py::TestComments::test_percent_is_not_special

### 2.5 Failed blocks

- tests/test_spec_bibtex.py::TestFailedBlocks::test_kinds_and_warning
- tests/test_spec_bibtex.py::TestFailedBlocks::test_at_starts_a_block
- tests/test_spec_bibtex.py::TestFailedBlocks::test_written_back_unchanged
- tests/test_spec_bibtex.py::TestFailedBlocks::test_field_names_and_keys_ignore_case
- tests/test_unreadable.py::TestUnreadable::test_case
- tests/test_unreadable.py::TestUnreadable::test_text_kept
- tests/test_unreadable.py::TestUnreadable::test_added_bibtex_warns
- tests/test_unchanged_save.py::TestReadWrite::test_unreadable_blocks_stay_as_they_are

### 2.6 Duplicate keys

- tests/test_spec_bibtex.py::TestDuplicateKeys::test_first_is_read
- tests/test_spec_bibtex.py::TestDuplicateKeys::test_strings
- tests/test_unreadable.py::TestUnreadable::test_case

### 2.7 Parse cache

- tests/test_parsecache.py::TestParseCache::test_cases
- tests/test_parsecache.py::TestParseCache::test_files_of_the_tests
- tests/test_parsecache.py::TestParseCache::test_not_cached_when_a_block_fails

### 3.1 Block order

- tests/test_spec_bibtex.py::TestBlockOrder::test_order
- tests/test_sort_format.py::TestSortFormat::test_sort_format_unchanged
- tests/test_sort_format.py::TestSortFormat::test_same_order_as_bibtexparser

### 3.2 Layout of each block

- tests/test_spec_bibtex.py::TestLayout::test_entry
- tests/test_spec_bibtex.py::TestLayout::test_entry_without_fields
- tests/test_spec_bibtex.py::TestLayout::test_multiline_value
- tests/test_spec_bibtex.py::TestLayout::test_other_blocks_and_separators
- tests/test_spec_bibtex.py::TestLayout::test_failed_block_last
- tests/test_spec_bibtex.py::TestLayout::test_empty_library
- tests/test_spec_bibtex.py::TestLayout::test_warning_line_removed_at_reading
- tests/test_spec_bibtex.py::TestFailedBlocks::test_written_back_unchanged
- tests/test_sort_format.py::TestSortFormat::test_sort_format_unchanged
- tests/test_sort_format.py::TestSortFormat::test_save_unchanged

### 3.3 Values

- tests/test_spec_bibtex.py::TestValues::test_braces
- tests/test_spec_bibtex.py::TestValues::test_bare_value_that_cannot_stay_bare
- tests/test_spec_bibtex.py::TestValues::test_value_set_by_papers
- tests/test_spec_bibtex.py::TestValues::test_example
- tests/test_spec_bibtex.py::TestValues::test_merge_keeps_bare
- tests/test_spec_bibtex.py::TestEntries::test_values
- tests/test_merge_dup_unit.py::test_bare_value_stays_bare

### 3.4 When the file is written

- tests/test_spec_bibtex.py::TestWhenWritten::test_unchanged_text_not_written
- tests/test_spec_bibtex.py::TestWhenWritten::test_changed_on_disk_refused
- tests/test_bib_fix.py::TestBiblio::test_save_without_change_does_not_write
- tests/test_safe_writes.py::TestChangedSinceRead::test_refused
- tests/test_safe_writes.py::TestChangedSinceRead::test_same_content
- tests/test_safe_writes.py::TestWriteAtomic::test_write
- tests/test_safe_writes.py::TestWriteAtomic::test_symlink

### 3.5 What is normalized

- tests/test_spec_bibtex.py::TestNormalized::test_only_layout
- tests/test_spec_bibtex.py::TestNormalized::test_name_formatting
- tests/test_entries.py::test_standard_name_braces
- tests/test_check.py::TestCheckFormatName::test_check_format_name
- tests/test_bib_fix.py::TestFixEntry::test_key_ascii

### 3.6 The DOI parser of `check --fix-doi` (informative)

- tests/test_check.py::TestCheckFixDoi::test_check_fix_doi
- tests/test_bib_fix.py::TestFixEntry::test_fix_doi
- tests/test_check.py::TestFixEntryBadDoi::test_other_fixes_still_applied
- tests/test_extract_unit.py::TestParseDoi::test_strips_doi_prefix
- tests/test_extract_unit.py::TestParseDoi::test_strips_unbalanced_trailing_paren
- tests/test_extract_unit.py::TestParseDoiCandidates::test_prefers_article_doi_over_data_repository
- tests/test_extract_unit.py::TestTextDoiCandidates::test_doi_glued_to_a_word_or_number_is_ignored

### 4.1 LaTeX to Unicode (identity and file names)

- tests/test_spec_bibtex.py::TestLatexToUnicode::test_accents
- tests/test_spec_bibtex.py::TestLatexToUnicode::test_characters
- tests/test_spec_bibtex.py::TestLatexToUnicode::test_other_commands
- tests/test_spec_bibtex.py::TestLatexToUnicode::test_text_signs
- tests/test_spec_bibtex.py::TestLatexToUnicode::test_paths
- tests/test_spec_bibtex.py::TestLatexToUnicode::test_unicode_to_latex_decodes_back
- tests/test_latexenc.py::TestLatexToUnicode::test_simple_accents
- tests/test_files_unit.py::TestCheckFiles::test_fix_mendeley_path_keeps_text_signs
- tests/test_spec_tables.py::TestSpecTables::test_latex_characters

### 4.2 Unicode to LaTeX (`check --encoding latex`)

- tests/test_spec_bibtex.py::TestUnicodeToLatex::test_check_encoding_latex
- tests/test_bib_fix.py::TestFixEntry::test_encoding_latex
- tests/test_latexenc.py::TestStringToLatex::test_preserves_spaces_and_braces

### 5.1 Syntax

- tests/test_spec_bibtex.py::TestFileSyntax::test_reading
- tests/test_spec_bibtex.py::TestFileSyntax::test_writing
- tests/test_entries.py::TestBibtexFileEntry::test_parse_file
- tests/test_entries.py::TestBibtexFileEntry::test_parse_files_trimmed
- tests/test_entries.py::TestBibtexFileEntry::test_parse_file_colon_in_path
- tests/test_entries.py::TestBibtexFileEntry::test_parse_file_empty_path_ignored
- tests/test_entries.py::TestBibtexFileEntry::test_format_files

### 5.2 Relative and absolute paths

- tests/test_spec_bibtex.py::TestFilePaths::test_relative_to_bibtex
- tests/test_spec_bibtex.py::TestFilePaths::test_one_file_however_written
- tests/test_spec_bibtex.py::TestFilePaths::test_no_link_left
- tests/test_spec_bibtex.py::TestFilePaths::test_rewritten_at_load
- tests/test_library_unit.py::TestGetBiblio::test_absolute_links_made_relative
- tests/test_library_unit.py::TestGetBiblio::test_relative_links_left_alone
- tests/test_library_unit.py::TestGetBiblio::test_link_on_another_drive_stays_absolute
- tests/test_unchanged_save.py::TestUnchangedSave::test_converted_links_are_saved

### 6. The `keywords` field and tags

- tests/test_spec_bibtex.py::TestTags::test_syntax
- tests/test_spec_bibtex.py::TestTags::test_add_remove_rename_ignore_case
- tests/test_spec_bibtex.py::TestTags::test_counting
- tests/test_spec_bibtex.py::TestTags::test_matching
- tests/test_spec_bibtex.py::TestTwoWayMerge::test_keywords_conflict
- tests/test_entries.py::test_tags_without_case
- tests/test_entry_cmds.py::TestTag::test_add
- tests/test_entry_cmds.py::TestTag::test_rm
- tests/test_entry_cmds.py::TestTag::test_rename_merges
- tests/test_entry_cmds.py::TestNestedTags::test_list_tag
- tests/test_entry_cmds.py::TestNestedTags::test_rename
- tests/test_entry_cmds.py::TestNestedTags::test_rename_nested

### 7.1 The `ids` field

- tests/test_spec_bibtex.py::TestIds::test_read_and_selected
- tests/test_spec_bibtex.py::TestIds::test_keep_old_key_written
- tests/test_entry_cmds.py::TestEditSet::test_keep_old_key
- tests/test_entry_cmds.py::TestEditSet::test_keep_old_key_once
- tests/test_duplicates.py::TestCheckOnDuplicate::test_ids_appended_without_repetition

### 7.2 Key validity on rename

- tests/test_spec_bibtex.py::TestKeyValidity::test_refused
- tests/test_entry_cmds.py::TestEditSet::test_key_refused
- tests/test_entry_cmds.py::TestEditSet::test_set_refused

### 7.3 `crossref` follows renames

- tests/test_spec_bibtex.py::TestCrossref::test_follows_renames
- tests/test_entry_cmds.py::TestEditSet::test_key
- tests/test_entry_cmds.py::TestEditSet::test_fix_key
- tests/test_duplicates.py::test_crossref_follows_the_merge

### 8. Key collisions when entries are added

- tests/test_spec_bibtex.py::TestKeySuffix::test_suffix_rule
- tests/test_spec_bibtex.py::TestKeySuffix::test_entry_without_key
- tests/test_spec_bibtex.py::TestKeySuffix::test_given_key_taken
- tests/test_spec_bibtex.py::TestKeySuffix::test_empty_template_key
- tests/test_entry_cmds.py::TestAddEmptyKey::test_add
- tests/test_bib_unit.py::TestAppendAbc::test_ignores_case
- tests/test_bib_unit.py::TestAppendAbc::test_upper_case_suffix
- tests/test_bib_unit.py::TestAppendAbc::test_after_z
- tests/test_bib_fix.py::TestFixEntry::test_auto_key_keeps_a_right_key
- tests/test_bib_fix.py::TestBiblio::test_same_key_other_paper
- tests/test_bib_fix.py::TestBiblio::test_same_key_title_by_case
- tests/test_bib_fix.py::TestBiblio::test_same_key_same_title_merges_files
- tests/test_duplicates.py::TestAddDialogue::test_n_same_key_gets_a_free_key

### 9.1 Text normalization

- tests/test_spec_bibtex.py::TestNormalization::test_norm
- tests/test_bib_unit.py::TestEntryId::test_author_id_accents
- tests/test_bib_unit.py::TestEntryId::test_title_id_braces_and_spaces
- tests/test_duplicates.py::TestIdentifiers::test_author_title_accents
- tests/test_spec_tables.py::TestSpecTables::test_ascii_transliteration

### 9.2 Identifiers of an entry

- tests/test_spec_bibtex.py::TestIdentifiersOfAnEntry::test_doi
- tests/test_spec_bibtex.py::TestIdentifiersOfAnEntry::test_arxiv
- tests/test_spec_bibtex.py::TestIdentifiersOfAnEntry::test_isbn
- tests/test_spec_bibtex.py::TestIdentifiersOfAnEntry::test_authors_and_title
- tests/test_duplicates.py::TestIdentifiers::test_arxiv_eprint
- tests/test_duplicates.py::TestIdentifiers::test_other_archive_is_not_arxiv
- tests/test_duplicates.py::TestIdentifiers::test_isbn_ignored_for_chapters
- tests/test_merge_dup_unit.py::TestDuplicate::test_parse_name
- tests/test_merge_dup_unit.py::TestDuplicate::test_split_names_outside_braces
- tests/test_merge_dup_unit.py::TestDuplicate::test_isbn_prefix
- tests/test_bib_unit.py::TestEntryId::test_authortitle_id_needs_both

### 9.3 The rule

- tests/test_spec_bibtex.py::TestSamePaperRule::test_isbn_has_no_title_guard
- tests/test_spec_bibtex.py::TestSamePaperRule::test_title_guard_needs_both_titles
- tests/test_duplicates.py::TestDistinct::test_recorded_and_honoured
- tests/test_duplicates.py::TestIdentifiers::test_doi_case_and_prefix
- tests/test_duplicates.py::TestIdentifiers::test_different_dois_are_different_papers
- tests/test_duplicates.py::TestIdentifiers::test_different_arxiv_ids
- tests/test_duplicates.py::TestIdentifiers::test_isbn_books
- tests/test_duplicates.py::TestIdentifiers::test_isbn_different_books
- tests/test_duplicates.py::TestIdentifiers::test_author_title
- tests/test_duplicates.py::TestIdentifiers::test_title_without_authors_is_not_enough
- tests/test_duplicates.py::TestIdentifiers::test_one_doi_only_falls_back_to_author_title
- tests/test_duplicates.py::TestIdentifiers::test_order_doi_before_arxiv
- tests/test_duplicates.py::TestIdentifiers::test_order_arxiv_before_author_title
- tests/test_duplicates.py::TestIdentifiers::test_order_isbn_before_author_title
- tests/test_duplicates.py::TestTitleGuard::test_types_and_titles_differ
- tests/test_duplicates.py::TestTitleGuard::test_same_type_always_same
- tests/test_duplicates.py::TestTitleGuard::test_titles_equal_after_normalization
- tests/test_duplicates.py::TestTitleGuard::test_arxiv_guard

### 9.4 `distinct.json`

- tests/test_spec_bibtex.py::TestDistinctFile::test_format
- tests/test_spec_bibtex.py::TestDistinctFile::test_reading
- tests/test_spec_bibtex.py::TestDistinctFile::test_matching
- tests/test_spec_bibtex.py::TestDistinctFile::test_in_the_library_folder
- tests/test_spec_bibtex.py::TestDistinctFile::test_union
- tests/test_duplicates.py::TestDistinct::test_recorded_and_honoured
- tests/test_duplicates.py::TestDistinct::test_identities_not_keys
- tests/test_duplicates.py::TestDistinct::test_does_not_leak_to_other_entries
- tests/test_duplicates.py::TestDistinct::test_update
- tests/test_duplicates.py::TestCheckDialogue::test_n_remembered
- tests/test_duplicates.py::TestAddDialogue::test_n
- tests/test_merge_dup_unit.py::TestDuplicate::test_distinct_unreadable
- tests/test_merge_dup_unit.py::TestDuplicate::test_distinct_add_without_identity
- tests/test_merge_dup_unit.py::TestDuplicate::test_side_matches_empty
- tests/test_bib_fix.py::TestBiblio::test_save_keeps_a_backup_and_the_distinct_pairs

### 9.5 Finding duplicates

- tests/test_spec_bibtex.py::TestFindingDuplicates::test_add_candidates
- tests/test_spec_bibtex.py::TestFindingDuplicates::test_groups
- tests/test_duplicates.py::TestGroups::test_copy_without_doi_goes_with_one_entry
- tests/test_duplicates.py::TestGroups::test_ask_group
- tests/test_duplicate_equivalence.py::TestEquivalence::test_find_duplicates
- tests/test_duplicate_equivalence.py::TestEquivalence::test_duplicate_groups

### 10.1 Target

- tests/test_duplicates.py::TestMerge::test_model
- tests/test_duplicates.py::TestMerge::test_with_target
- tests/test_duplicates.py::TestCheckDialogue::test_t
- tests/test_duplicates.py::TestGroups::test_copy_without_doi_goes_with_one_entry

### 10.2 Fields

- tests/test_spec_bibtex.py::TestTwoWayMerge::test_fields
- tests/test_merge_dup_unit.py::TestMerge::test_empty_values
- tests/test_merge_dup_unit.py::test_empty_field_not_added
- tests/test_duplicates.py::TestMerge::test_model

### 10.3 Equivalent values

- tests/test_spec_bibtex.py::TestTwoWayMerge::test_equivalent_values
- tests/test_spec_bibtex.py::TestTwoWayMerge::test_preferred_value
- tests/test_duplicates.py::TestNames::test_initials
- tests/test_duplicates.py::TestNames::test_different_first_names
- tests/test_duplicates.py::TestNames::test_fuller_form_kept_from_either_side
- tests/test_duplicates.py::TestNames::test_different_names_conflict

### 10.4 `file`

- tests/test_spec_bibtex.py::TestTwoWayMerge::test_files_by_content
- tests/test_duplicates.py::TestMerge::test_files_by_real_path
- tests/test_duplicates.py::TestMerge::test_model

### 10.5 `ids`

- tests/test_spec_bibtex.py::TestTwoWayMerge::test_ids
- tests/test_duplicates.py::TestMerge::test_keys_to_ids
- tests/test_duplicates.py::TestMerge::test_no_ids_in_add
- tests/test_duplicates.py::TestCheckOnDuplicate::test_ids_appended_without_repetition

### 10.6 Decision

- tests/test_duplicates.py::TestAddOnDuplicate::test_exact_duplicate_never_asks
- tests/test_duplicates.py::TestAddOnDuplicate::test_keep
- tests/test_duplicates.py::TestAddOnDuplicate::test_update
- tests/test_duplicates.py::TestAddOnDuplicate::test_skip
- tests/test_duplicates.py::TestAddOnDuplicate::test_error_exit_status
- tests/test_duplicates.py::TestAddOnDuplicate::test_default_without_terminal_is_error
- tests/test_duplicates.py::TestCheckOnDuplicate::test_keep
- tests/test_duplicates.py::TestCheckOnDuplicate::test_skip
- tests/test_duplicates.py::TestCheckOnDuplicate::test_update_not_available
- tests/test_duplicates.py::TestAddDialogue::test_title_guard_asks
- tests/test_duplicates.py::TestAddDialogue::test_n
- tests/test_duplicates.py::TestAddDialogue::test_n_same_key_gets_a_free_key
- tests/test_duplicates.py::TestCheckDialogue::test_n_remembered

### 10.7 Result

- tests/test_duplicates.py::TestMerge::test_model
- tests/test_duplicates.py::TestCheckDialogue::test_1
- tests/test_merge_dup_unit.py::test_bare_value_stays_bare
- tests/test_spec_bibtex.py::TestValues::test_merge_keeps_bare

### 10.8 Three-way merge

- in exchange.md, section 5.

## formats.md

### Conventions

- tests/test_spec_formats.py::TestCSLExportFields::test_values
- tests/test_spec_formats.py::TestBibJSONReading::test_values (an object without `name`)

### 1. Formats and where they are used

- tests/test_spec_formats.py::TestFormatsTable::test_ids_and_file_names
- tests/test_formats.py::TestExportFormats::test_all

### 1.1 Format of a file from its name

- tests/test_spec_formats.py::TestFormatOfAFile::test_extensions
- tests/test_formats.py::TestBibJSON::test_file_format
- tests/test_formats.py::TestAddFormats::test_format_option
- tests/test_formats.py::TestAddFormats::test_bibtex_by_default

### 1.2 Commands

- tests/test_formats.py::TestAddFormats::test_add_json_duplicates
- tests/test_formats.py::TestAddFormats::test_add_ris_with_file
- tests/test_formats.py::TestAddFormats::test_add_bibjson
- tests/test_formats.py::TestAddFormats::test_format_option
- tests/test_formats.py::TestAddFormats::test_metadata_one_entry_only
- tests/test_spec_formats.py::TestCommands::test_recursive_reads_pdf_and_bib_only
- tests/test_entry_cmds.py::TestEditFrom::test_from_file
- tests/test_entry_cmds.py::TestEditFrom::test_from_file_with_file_and_keywords
- tests/test_entry_cmds.py::TestEditFrom::test_from_ris
- tests/test_entry_cmds.py::TestEditFrom::test_from_stdin_pipe
- tests/test_entry_cmds.py::TestEditFrom::test_two_entries
- tests/test_entry_cmds.py::TestEditFrom::test_errors
- tests/test_spec_formats.py::TestCommands::test_from_stdin_with_format
- tests/test_spec_formats.py::TestCommands::test_format_without_from
- tests/test_formats.py::TestListFormats::test_csl_json
- tests/test_list_actions.py::TestListFileActions::test_export
- tests/test_list_actions.py::TestListFileActions::test_export_files

### 1.3 Text encoding

- tests/test_spec_formats.py::TestTextEncoding::test_read_bom_and_crlf
- tests/test_spec_formats.py::TestTextEncoding::test_ris_lone_cr
- tests/test_spec_formats.py::TestTextEncoding::test_written_utf8_lf
- tests/test_formats.py::TestRIS::test_endnote_export
- tests/test_formats.py::TestExportFormats::test_line_ends

### 2.1 Values as text (export)

- tests/test_spec_formats.py::TestValuesAsText::test_raw_fields
- tests/test_spec_formats.py::TestValuesAsText::test_text_without_latex_is_trimmed_only
- tests/test_spec_formats.py::TestValuesAsText::test_latex_decoded

### 2.2 Names: bibtex to parts

- tests/test_spec_formats.py::TestNamesToParts::test_examples
- tests/test_formats.py::TestNames::test_parse
- tests/test_formats.py::TestNames::test_one_word_and_braces
- tests/test_formats.py::TestNames::test_more_commas
- tests/test_formats.py::TestNames::test_suffix_without_given

### 2.3 Names: parts to bibtex

- tests/test_spec_formats.py::TestPartsToNames::test_rules
- tests/test_formats.py::TestNames::test_format
- tests/test_formats.py::TestNames::test_suffix_without_given

### 2.4 Dates

- tests/test_spec_formats.py::TestDates::test_date_text
- tests/test_spec_formats.py::TestDates::test_date_of_an_entry
- tests/test_spec_formats.py::TestDates::test_month_numbers
- tests/test_spec_formats.py::TestDates::test_date_to_fields
- tests/test_formats.py::TestDates::test_zero_or_missing_part_ends_the_date

### 2.5 Pages

- tests/test_spec_formats.py::TestPages::test_to_bibtex
- tests/test_spec_formats.py::TestPages::test_first_and_last
- tests/test_spec_formats.py::TestPages::test_first_and_last_ris

### 2.6 DOI

- tests/test_spec_formats.py::TestDOI::test_clean

### 2.7 Keys of imported entries

- tests/test_spec_formats.py::TestKeys::test_usable_keys
- tests/test_formats.py::TestCSL::test_key
- tests/test_formats.py::TestAddFormats::test_add_json_duplicates
- tests/test_entry_cmds.py::TestEditFrom::test_from_file

### 2.8 File links of imported entries

- tests/test_spec_formats.py::TestFileLinks::test_items
- tests/test_spec_formats.py::TestFileLinks::test_string_split
- tests/test_spec_formats.py::TestEditFromLinks::test_relative_to_file
- tests/test_spec_formats.py::TestEditFromLinks::test_stdin_as_written
- tests/test_formats.py::TestCSL::test_file_key
- tests/test_formats.py::TestRIS::test_file_links
- tests/test_formats.py::TestRIS::test_endnote_export
- tests/test_formats.py::TestAddFormats::test_add_ris_with_file
- tests/test_entry_cmds.py::TestEditFrom::test_from_file_links_relative_to_file

### 2.9 LaTeX special characters of imported values

- tests/test_spec_formats.py::TestLatexEscape::test_escaped_fields
- tests/test_spec_formats.py::TestLatexEscape::test_bibjson_unchanged
- tests/test_spec_formats.py::TestLatexEscape::test_ris_escaped
- tests/test_formats.py::TestCSL::test_latex_special_characters
- tests/test_formats.py::TestRIS::test_latex_special_characters

### 3.1 Entry types

- tests/test_spec_formats.py::TestCSLTypes::test_export
- tests/test_spec_formats.py::TestCSLTypes::test_import
- tests/test_formats.py::TestCSL::test_types

### 3.2 Fields, export

- tests/test_spec_formats.py::TestCSLExportFields::test_key_order
- tests/test_spec_formats.py::TestCSLExportFields::test_publisher_fallback_and_genre
- tests/test_spec_formats.py::TestCSLExportFields::test_container_issue_keywords
- tests/test_spec_formats.py::TestCSLExportFields::test_dates
- tests/test_spec_formats.py::TestCSLExportFields::test_values
- tests/test_formats.py::TestCSL::test_article
- tests/test_formats.py::TestCSL::test_publisher_position
- tests/test_formats.py::TestCSL::test_schema

### 3.3 Fields, import

- tests/test_spec_formats.py::TestCSLImportFields::test_simple_fields
- tests/test_spec_formats.py::TestCSLImportFields::test_number_pages_publisher_genre
- tests/test_spec_formats.py::TestCSLImportFields::test_keywords
- tests/test_spec_formats.py::TestCSLImportFields::test_issued_and_accessed
- tests/test_spec_formats.py::TestCSLImportFields::test_files_and_key
- tests/test_formats.py::TestCSL::test_container_title
- tests/test_formats.py::TestCSL::test_zotero_export
- tests/test_formats.py::TestCSL::test_round_trip

### 3.4 Document layout

- tests/test_spec_formats.py::TestCSLDocument::test_reading
- tests/test_spec_formats.py::TestCSLDocument::test_add_error_exit
- tests/test_spec_formats.py::TestCSLDocument::test_example
- tests/test_formats.py::TestCSL::test_not_csl

### 3.5 What is lost

- tests/test_spec_formats.py::TestCSLLost::test_round_trip
- tests/test_formats.py::TestCSL::test_round_trip

### 4.1 Line syntax

- tests/test_spec_formats.py::TestRISLines::test_tag_lines
- tests/test_formats.py::TestRIS::test_tag_without_space_after_dash

### 4.2 Reading

- tests/test_spec_formats.py::TestRISReading::test_records
- tests/test_spec_formats.py::TestRISReading::test_continuation
- tests/test_spec_formats.py::TestRISReading::test_stray_lines
- tests/test_spec_formats.py::TestRISReading::test_single_and_list_tags
- tests/test_spec_formats.py::TestRISReading::test_unknown_tags_and_errors
- tests/test_formats.py::TestRIS::test_blank_line_after_ty
- tests/test_formats.py::TestRIS::test_tag_without_space_after_dash
- tests/test_formats.py::TestRIS::test_last_record_without_er
- tests/test_formats.py::TestRIS::test_not_ris
- tests/test_formats.py::TestRIS::test_endnote_export
- tests/test_formats.py::TestRIS::test_wos_export

### 4.3 Writing

- tests/test_spec_formats.py::TestRISWriting::test_example (the example with a plain title, and the file name of its template)
- tests/test_spec_formats.py::TestRISWriting::test_no_entries
- tests/test_spec_formats.py::TestRISWriting::test_tags
- tests/test_spec_formats.py::TestRISWriting::test_dates
- tests/test_formats.py::TestRIS::test_article
- tests/test_formats.py::TestRIS::test_urldate_and_translator
- tests/test_formats.py::TestRIS::test_container_and_suffix
- tests/test_formats.py::TestRIS::test_mastersthesis

### 4.4 Entry types

- tests/test_spec_formats.py::TestRISTypes::test_export
- tests/test_spec_formats.py::TestRISTypes::test_import
- tests/test_formats.py::TestRIS::test_mastersthesis

### 4.5 Fields, import

- tests/test_spec_formats.py::TestRISImportFields::test_names
- tests/test_spec_formats.py::TestRISImportFields::test_ris_names
- tests/test_spec_formats.py::TestRISImportFields::test_titles_and_container
- tests/test_spec_formats.py::TestRISImportFields::test_dates
- tests/test_spec_formats.py::TestRISImportFields::test_pages
- tests/test_spec_formats.py::TestRISImportFields::test_identifiers
- tests/test_spec_formats.py::TestRISImportFields::test_other_fields
- tests/test_formats.py::TestRIS::test_endnote_export
- tests/test_formats.py::TestRIS::test_wos_export
- tests/test_formats.py::TestRIS::test_doi_from_a_url_next_to_another
- tests/test_formats.py::TestRIS::test_container_and_suffix
- tests/test_formats.py::TestRIS::test_urldate_and_translator
- tests/test_formats.py::TestRIS::test_round_trip

### 4.6 What is lost

- tests/test_spec_formats.py::TestRISLost::test_keyword_with_semicolon

### 5.1 Writing

- tests/test_spec_formats.py::TestBibJSONWriting::test_example
- tests/test_spec_formats.py::TestBibJSONWriting::test_without_namespace
- tests/test_formats.py::TestBibJSON::test_article
- tests/test_formats.py::TestBibJSON::test_field_named_as_a_bibjson_key

### 5.2 Reading

- tests/test_spec_formats.py::TestBibJSONReading::test_records
- tests/test_spec_formats.py::TestBibJSONReading::test_type_key_and_skipped
- tests/test_spec_formats.py::TestBibJSONReading::test_values
- tests/test_spec_formats.py::TestBibJSONReading::test_doi_and_file
- tests/test_formats.py::TestBibJSON::test_json_values
- tests/test_formats.py::TestBibJSON::test_numbers_as_written_and_null_items
- tests/test_formats.py::TestBibJSON::test_spec_examples
- tests/test_formats.py::TestBibJSON::test_one_record_or_list
- tests/test_formats.py::TestBibJSON::test_not_bibjson

### 5.3 What is lost

- tests/test_spec_formats.py::TestBibJSONLost::test_round_trip
- tests/test_formats.py::TestBibJSON::test_round_trip

### 6. `papers list` output

- tests/test_spec_formats.py::TestListOutput::test_no_entry
- tests/test_spec_formats.py::TestListOutput::test_bibtex
- tests/test_spec_formats.py::TestListOutput::test_field
- tests/test_spec_formats.py::TestListOutput::test_other_formats_paths
- tests/test_spec_formats.py::TestListOutput::test_line_format
- tests/test_list.py::FormattingTest::test_format
- tests/test_list.py::FormattingTest::test_format_option
- tests/test_list.py::FormattingTest::test_format_exclusive
- tests/test_list.py::FormattingTest::test_color
- tests/test_list_more.py::TestListFilters::test_field
- tests/test_deprecated.py::TestRenamedOptions::test_list_f
- tests/test_formats.py::TestListFormats::test_csl_json
- tests/test_formats.py::TestListFormats::test_bibjson
- tests/test_formats.py::TestListFormats::test_ris

### 6.1 Search

- tests/test_spec_formats.py::TestListOutput::test_search_normalized
- tests/test_list.py::SearchTest::test_list_title
- tests/test_list.py::SearchTest::test_list_title_fuzzy
- tests/test_list.py::SearchTest::test_list_title_multiple
- tests/test_list.py::SearchTest::test_list_author
- tests/test_list.py::SearchTest::test_list_first_author
- tests/test_list.py::SearchTest::test_list_key
- tests/test_list.py::SearchTest::test_list_year
- tests/test_list.py::SearchTest::test_list_combined
- tests/test_list.py::SearchTest::test_list_fullsearch

### 7. `--porcelain`

- those of 7.1 and 7.2.

### 7.1 Streams

- tests/test_porcelain.py::TestPorcelain::test_other_messages_on_stderr
- tests/test_porcelain.py::TestPorcelain::test_list_on_stdout
- tests/test_porcelain.py::TestPorcelain::test_stdout_restored
- tests/test_spec_formats.py::TestPorcelainStreams::test_formats_on_stdout

### 7.2 Porcelain lines

- tests/test_porcelain.py::TestPorcelain::test_add
- tests/test_porcelain.py::TestPorcelain::test_add_skipped_duplicate_is_existing
- tests/test_porcelain.py::TestPorcelain::test_tag_and_rm
- tests/test_porcelain.py::TestPorcelain::test_list_on_stdout
- tests/test_entry_cmds.py::TestEditSet::test_key
- tests/test_entry_cmds.py::TestEditSet::test_fix_key
- tests/test_spec_formats.py::TestPorcelainStreams::test_commands_without_lines
- tests/test_spec_formats.py::TestPorcelainLines::test_order
- tests/test_spec_formats.py::TestPorcelainLines::test_existing_only_for_add
- tests/test_spec_formats.py::TestPorcelainLines::test_content_equality
- tests/test_spec_formats.py::TestPorcelainLines::test_add_lines
- tests/test_spec_formats.py::TestPorcelainCommands::test_file_commands
- tests/test_spec_formats.py::TestPorcelainCommands::test_history_revert
- tests/test_spec_formats.py::TestPorcelainConfigPool::test_config_pool. The human lines: none (free).

### 7.3 Exit codes and standard error

- tests/test_spec_formats.py::TestExitCodes::test_codes
- tests/test_spec_formats.py::TestExitCodes::test_question_without_input
- tests/test_cli_unit.py::TestMainCleanExit::test_papers_exit
- tests/test_cli_unit.py::TestMainCleanExit::test_eof
- tests/test_cli_unit.py::TestBrokenPipe::test_no_traceback
- tests/test_cli_unit.py::TestInterrupt::test_ctrl_c
- tests/test_options.py::TestUnknownOptions::test_command_does_not_run
- tests/test_options.py::TestUnknownOptions::test_subcommand

### 8. JSON text format

- tests/test_spec_formats.py::TestJSONText::test_bytes
- tests/test_spec_formats.py::TestCSLDocument::test_example
- tests/test_spec_formats.py::TestBibJSONWriting::test_example
- tests/test_spec_formats.py::TestListOutput::test_no_entry

### 9. `papers export` layout

- tests/test_spec_formats.py::TestExportLayout::test_dir
- tests/test_spec_formats.py::TestExportLayout::test_format_names
- tests/test_spec_formats.py::TestExportLayout::test_new_library
- tests/test_spec_formats.py::TestExportLayout::test_files
- tests/test_pools.py::TestExport::test_copy
- tests/test_pools.py::TestExport::test_selection_and_link
- tests/test_pools.py::TestExport::test_none
- tests/test_pools.py::TestExport::test_not_empty
- tests/test_formats.py::TestExportFormats::test_default_bib
- tests/test_formats.py::TestExportFormats::test_all
- tests/test_formats.py::TestExportFormats::test_csl_only
- tests/test_formats.py::TestExportFormats::test_repeated_and_comma
- tests/test_formats.py::TestExportFormats::test_bibjson
- tests/test_formats.py::TestExportFormats::test_files_none
- tests/test_formats.py::TestExportFormats::test_unknown_format

## exchange.md

### 2.1 Which pool

- tests/test_pools.py::TestResolution::test_no_pool_setting
- tests/test_pools_more.py::TestPullEntries::test_no_pool
- tests/test_pools_more.py::TestPullEntries::test_other_pool
- tests/test_pools.py::TestAdd::test_no_pool
- tests/test_exchanges.py::TestAddPool::test_errors
- tests/test_exchanges.py::TestAddPool::test_new_entry_is_not_sent
- tests/test_exchanges.py::TestShallowWithOther::test_pull

### 2.2 Rules on a pool (contract for the conditions)

- tests/test_pools.py::TestResolution::test_errors
- tests/test_pools.py::TestConfigPoolSelfContained::test_init_pool_must_be_a_library_without_pool
- tests/test_pools.py::TestResolution::test_never_itself
- tests/test_pools.py::TestResolution::test_missing_library_is_never_created
- tests/test_pools.py::TestResolution::test_push_to_missing_pool
- tests/test_pools.py::TestPull::test_missing_pool
- tests/test_exchanges.py::TestShallowWithOther::test_other_must_have_no_pool
- tests/test_pools.py::TestConfigPoolSelfContained::test_configured_pool_that_takes_a_pool
- tests/test_pools.py::TestConfigPoolSelfContained::test_config_pool_not_the_library_itself
- tests/test_pools_onetime.py::TestOneTime::test_pool_option_with_the_pool_of_the_library
- tests/test_unreadable.py::TestUnreadable::test_push_refused
- tests/test_unreadable.py::TestUnreadable::test_pull_allowed
- tests/test_lock.py::TestCommands::test_pool_locked_too
- tests/test_spec_exchange.py::TestPoolRules::test_configured_pool_with_a_pool_auto_push_warns
- tests/test_spec_exchange.py::TestPoolRules::test_unreadable_pool_stops_the_automatic_push

### 2.3 The pool id (contract)

- tests/test_pools.py::TestResolution::test_path_and_cache
- tests/test_pools_more.py::TestPoolLookups::test_pool_path_given_as_in_setting
- tests/test_pools_more.py::TestPoolLookups::test_repr_and_label
- tests/test_pools_more.py::TestPoolLookups::test_label_of_the_pool_option
- tests/test_pools_more.py::TestPoolIdentifier::test_library_moved
- tests/test_pools_more.py::TestPoolIdentifier::test_two_path_ids_move_together
- tests/test_pools_onetime.py::TestOneTime::test_config_pool_finds_the_records
- tests/test_spec_exchange.py::TestPoolId::test_identifier_format
- tests/test_spec_exchange.py::TestPoolId::test_other_library_relative_id
- tests/test_spec_exchange.py::TestPoolId::test_path_ids_in_sorted_order
- tests/test_spec_exchange.py::TestPoolId::test_identifier_after_first_step

### 3.1 Files (contract)

- tests/test_pools.py::TestOrigin::test_file_names
- tests/test_pools_more.py::TestPoolIdentifier::test_file_named_after_the_pool_folder
- tests/test_library_folder.py::LibraryFolderTest::test_origin_in_library_folder
- tests/test_pools_onetime.py::TestOneTime::test_config_pool_finds_the_records
- tests/test_spec_exchange.py::TestOriginFiles::test_file_name_examples
- tests/test_spec_exchange.py::TestOriginFiles::test_identifier_file_named_after_the_folder

### 3.2 Format (contract)

- tests/test_pools.py::TestOrigin::test_one_file_per_pool
- tests/test_pools_more.py::TestPoolIdentifier::test_library_moved
- tests/test_spec_exchange.py::TestOriginFormat::test_exact_text
- tests/test_spec_exchange.py::TestOriginFormat::test_pool_path_follows_the_pool

### 3.3 What a record holds (contract)

- tests/test_pools.py::TestOrigin::test_roundtrip
- tests/test_pools.py::TestPull::test_record_without_the_pool_ids
- tests/test_pools.py::TestPull::test_pool_change_taken_library_change_kept
- tests/test_pools.py::TestPush::test_pool_only_fields_come_with_the_next_pull
- tests/test_pools.py::TestPush::test_push_keeps_a_pool_change
- tests/test_auto_push.py::TestShallowSharedLinks::test_record_keeps_the_file_field
- tests/test_auto_push.py::TestShallowSharedLinks::test_record_of_development_builds
- tests/test_exchanges.py::TestAddPool::test_self_contained
- tests/test_spec_exchange.py::TestRecordContent::test_time_format
- tests/test_pools.py::TestShallow::test_link_removed_in_pool
- tests/test_spec_exchange.py::TestRecordContent::test_push_of_a_new_entry
- tests/test_spec_exchange.py::TestRecordContent::test_record_ids_ignored_as_base

### 3.4 Reading (contract)

- tests/test_pools.py::TestOrigin::test_roundtrip
- tests/test_pools.py::TestOrigin::test_one_file_per_pool
- tests/test_pools.py::TestOrigin::test_two_files_of_one_pool
- tests/test_spec_exchange.py::TestOriginReading::test_comments
- tests/test_spec_exchange.py::TestOriginReading::test_files_ignored
- tests/test_spec_exchange.py::TestOriginReading::test_keys_without_case
- tests/test_spec_exchange.py::TestOriginReading::test_utf8_with_bom

### 3.5 Writing (contract for the content; free for the timing)

- tests/test_pools.py::TestOrigin::test_roundtrip
- tests/test_pools.py::TestOrigin::test_two_files_of_one_pool
- tests/test_pools.py::TestOrigin::test_history
- tests/test_pools.py::TestPull::test_nothing_to_pull_is_not_saved
- tests/test_pools.py::TestPull::test_conflict_skip
- tests/test_pools.py::TestPull::test_entry_not_in_the_pool
- tests/test_pools.py::TestAdd::test_new_entry_not_in_pool
- tests/test_pools.py::TestShallow::test_push_never_writes_empty_entry
- tests/test_pools_more.py::TestPoolIdentifier::test_two_path_ids_move_together
- tests/test_spec_exchange.py::TestOriginWriting::test_same_record_keeps_its_time
- tests/test_spec_exchange.py::TestOriginWriting::test_unchanged_file_not_written
- tests/test_spec_exchange.py::TestOriginWriting::test_dry_run_writes_nothing
- tests/test_spec_exchange.py::TestOriginWriting::test_add_keeps_an_existing_record

### 3.6 The exchange time `papers-pulled` (contract)

- tests/test_pools.py::TestPull::test_select
- tests/test_pools.py::TestPull::test_conflict_skip
- tests/test_pools.py::TestPull::test_check_and_status
- tests/test_pools.py::TestPush::test_status_after_push
- tests/test_pools.py::TestPush::test_pool_only_fields_come_with_the_next_pull
- tests/test_pools.py::TestStatus::test_after_add_from_pool
- tests/test_pools.py::TestStatus::test_partial_pull_is_not_an_exchange
- tests/test_pools.py::TestStatus::test_same_change_on_both_sides
- tests/test_pools.py::TestStatus::test_no_change_no_flip
- tests/test_pools.py::TestStatus::test_no_change_no_flip_shallow
- tests/test_pools.py::TestStatus::test_after_add_to_the_pool
- tests/test_spec_exchange.py::TestExchangeTime::test_value_is_the_pool_mtime
- tests/test_spec_exchange.py::TestExchangeTime::test_push_after_a_pool_change
- tests/test_spec_exchange.py::TestExchangeTime::test_link_update
- tests/test_spec_exchange.py::TestExchangeTime::test_later_add_keeps_the_time
- tests/test_spec_exchange.py::TestExchangeTime::test_quit_does_not_set_it

### 3.7 Renamed keys (contract)

- tests/test_pools.py::TestPull::test_key_changed
- tests/test_pools.py::TestPull::test_rename_onto_a_leftover_record
- tests/test_auto_push.py::TestAutoPush::test_edit_key
- tests/test_spec_exchange.py::TestRenamedKeys::test_replaced_in_every_pool
- tests/test_spec_exchange.py::TestRenamedKeys::test_shallow_library

### 3.8 Legacy file `.papers/origin.bib` (contract for reading)

- tests/test_pools.py::TestOrigin::test_migration
- tests/test_spec_exchange.py::TestLegacyOrigin::test_origin_dir_wins
- tests/test_spec_exchange.py::TestLegacyOrigin::test_dry_run_keeps_it

### 3.9 Records under a path id (contract)

- tests/test_pools_more.py::TestPoolIdentifier::test_library_moved
- tests/test_pools_more.py::TestPoolIdentifier::test_two_path_ids_move_together
- tests/test_spec_exchange.py::TestPathIdRecords::test_move
- tests/test_spec_exchange.py::TestPathIdRecords::test_status_writes_nothing
- tests/test_spec_exchange.py::TestPathIdRecords::test_other_path_id_stays

### 4.1 The pool entry of a library entry (contract)

- tests/test_pools.py::TestPull::test_recorded_pool_entry_among_same_papers
- tests/test_pools.py::TestPull::test_pool_key_of_another_paper
- tests/test_pools.py::TestPull::test_key_never_changes
- tests/test_pools.py::TestPull::test_entry_without_origin_is_shared
- tests/test_pools_more.py::TestPoolLookups::test_by_key
- tests/test_spec_exchange.py::TestPoolEntry::test_record_key_by_identity_of_the_entry
- tests/test_spec_exchange.py::TestPoolEntry::test_titles_changed_on_both_sides
- tests/test_spec_exchange.py::TestPoolEntry::test_reused_pool_key
- tests/test_spec_exchange.py::TestPoolEntry::test_distinct_pairs_of_both_sides
- tests/test_spec_exchange.py::TestPoolEntry::test_ask_verdict_is_no_match

### 4.2 The library entry of a pool entry (contract)

- tests/test_pools_more.py::TestPullEntries::test_pull_pool_key
- tests/test_pools_more.py::TestPullEntries::test_same_paper_in_library
- tests/test_pools_more.py::TestPullEntries::test_all
- tests/test_pools_more.py::TestPullEntries::test_key_taken
- tests/test_spec_exchange.py::TestLibraryEntry::test_record_of_the_pool_key_first

### 4.3 Shared, removed, without record

- tests/test_pools.py::TestPull::test_entry_not_in_the_pool
- tests/test_pools.py::TestPull::test_entry_without_origin_is_shared
- tests/test_pools_more.py::TestPullCheck::test_not_found_in_pool
- tests/test_pools_more.py::TestSync::test_not_found_only_for_keys_given
- tests/test_auto_push.py::TestRemovedFromThePool::test_push
- tests/test_auto_push.py::TestRemovedFromThePool::test_sync
- tests/test_auto_push.py::TestRemovedFromThePool::test_push_key_adds_it_back
- tests/test_auto_push.py::TestRemovedFromThePool::test_push_key_after_the_note
- tests/test_auto_push.py::TestRemovedFromThePool::test_auto_push
- tests/test_auto_push.py::TestAutoPush::test_rm_is_not_pushed
- tests/test_auto_push.py::TestSharedWithoutRecord::test_push

### 5.1 Sides (contract)

- tests/test_auto_push.py::TestOwnFields::test_push_keeps_the_library_ids
- tests/test_auto_push.py::TestOwnFields::test_pull_keeps_the_pool_ids
- tests/test_pools.py::TestPull::test_pool_change_taken_library_change_kept
- tests/test_pools.py::TestPush::test_changes
- tests/test_spec_exchange.py::TestSides::test_links_written_for_the_target

### 5.2 Fields each side keeps (contract)

- tests/test_pools.py::TestPull::test_key_never_changes
- tests/test_pools.py::TestPush::test_conflict_update
- tests/test_auto_push.py::TestOwnFields::test_push_keeps_the_library_ids
- tests/test_auto_push.py::TestOwnFields::test_pull_keeps_the_pool_ids
- tests/test_auto_push.py::TestOwnFields::test_pull_keeps_the_library_ids
- tests/test_merge3.py::TestThreeWay::test_ids_of_the_target_only
- tests/test_merge3.py::TestThreeWay::test_exchange_ids_of_the_target_only_without_base
- tests/test_pools.py::TestPull::test_new_pool_file
- tests/test_auto_push.py::TestShallowSharedLinks::test_pull_adds_the_links_the_pool_added
- tests/test_spec_exchange.py::TestThreeWayRule::test_entry_type

### 5.3 The three-way rule (contract)

- tests/test_merge3.py::TestThreeWay::test_unchanged
- tests/test_merge3.py::TestThreeWay::test_changed_in_pool_only_is_offered
- tests/test_merge3.py::TestThreeWay::test_changed_in_library_only_is_kept
- tests/test_merge3.py::TestThreeWay::test_changed_on_both_sides
- tests/test_merge3.py::TestThreeWay::test_same_change_on_both_sides
- tests/test_merge3.py::TestThreeWay::test_equivalent_change_in_pool_only_is_offered
- tests/test_merge3.py::TestThreeWay::test_equivalent_values_without_change_of_target
- tests/test_merge3.py::TestThreeWay::test_removed_in_pool_is_offered
- tests/test_merge3.py::TestThreeWay::test_removed_in_pool_changed_in_library_is_a_conflict
- tests/test_merge3.py::TestThreeWay::test_removed_in_library_changed_in_pool_is_a_conflict
- tests/test_merge3.py::TestThreeWay::test_removed_on_both_sides
- tests/test_merge3.py::TestThreeWay::test_removed_in_library_stays_removed
- tests/test_merge3.py::TestThreeWay::test_added_differently_on_both_sides
- tests/test_pools.py::TestPush::test_brace_fix_is_sent
- tests/test_auto_push.py::TestRemovals::test_removed_in_the_pool
- tests/test_auto_push.py::TestRemovals::test_removed_in_the_library
- tests/test_auto_push.py::TestRemovals::test_removed_on_both_sides
- tests/test_auto_push.py::TestRemovals::test_removed_on_one_side_changed_on_the_other
- tests/test_spec_exchange.py::TestThreeWayRule::test_table
- tests/test_spec_exchange.py::TestThreeWayRule::test_entry_type

### 5.4 Without base (contract)

- tests/test_merge3.py::TestThreeWay::test_no_base_one_side_only_is_an_addition
- tests/test_merge3.py::TestThreeWay::test_two_way_equivalent_values_unchanged
- tests/test_auto_push.py::TestOwnFields::test_first_exchange_does_not_merge_ids
- tests/test_pools.py::TestPull::test_entry_without_origin_is_shared
- tests/test_pools.py::TestPush::test_existing_pool_entry
- tests/test_spec_exchange.py::TestWithoutBase::test_table

### 5.5 Outcome (contract)

- tests/test_pools.py::TestPull::test_nothing_changed
- tests/test_pools.py::TestPull::test_nothing_to_pull_is_not_saved
- tests/test_pools.py::TestPull::test_entry_without_origin_is_linked
- tests/test_pools.py::TestPull::test_conflict_skip
- tests/test_pools.py::TestStatus::test_no_change_no_flip
- tests/test_spec_exchange.py::TestOutcome::test_linked_writes_a_record_only
- tests/test_spec_exchange.py::TestOutcome::test_skip_comes_again

### 5.6 `--on-duplicate` (contract for the decisions; free for the dialogue)

- tests/test_pools.py::TestPull::test_conflict_error
- tests/test_pools.py::TestPull::test_conflict_keep
- tests/test_pools.py::TestPull::test_conflict_update
- tests/test_pools.py::TestPull::test_conflict_skip
- tests/test_pools.py::TestPull::test_conflict_ask
- tests/test_pools.py::TestPush::test_conflict_keep
- tests/test_pools.py::TestPush::test_conflict_update
- tests/test_pools.py::TestPush::test_conflict_error
- tests/test_pools_more.py::TestPushConflict::test_skip
- tests/test_pools_more.py::TestPushConflict::test_update
- tests/test_pools_more.py::TestSync::test_conflict_stops_before_push
- tests/test_auto_push.py::TestAutoPush::test_conflict_does_not_stop_the_command
- tests/test_merge3.py::TestThreeWay::test_decline_addition
- tests/test_spec_exchange.py::TestOnDuplicate::test_sync_keep_and_update
- tests/test_spec_exchange.py::TestOnDuplicate::test_update_takes_a_removal
- tests/test_spec_exchange.py::TestOnDuplicate::test_additions_in_every_mode

### 6.1 Selection

- tests/test_pools.py::TestPull::test_select
- tests/test_pools.py::TestPull::test_entry_not_in_the_pool
- tests/test_pools_more.py::TestPullEntries::test_pull_pool_key
- tests/test_pools_more.py::TestPullEntries::test_pull_by_doi
- tests/test_pools_more.py::TestPullEntries::test_same_paper_in_library
- tests/test_pools_more.py::TestPullEntries::test_unknown
- tests/test_pools_more.py::TestPullEntries::test_all
- tests/test_spec_exchange.py::TestPullSelection::test_list_pull

### 6.2 Steps

- tests/test_pools.py::TestPull::test_distinct_merged
- tests/test_pools.py::TestPush::test_distinct_merged
- tests/test_pools.py::TestPull::test_entry_not_in_the_pool
- tests/test_pools_more.py::TestSync::test_not_found_only_for_keys_given
- tests/test_pools.py::TestShallow::test_pull_links_to_pool_files
- tests/test_exchanges.py::TestShallowWithOther::test_pull
- tests/test_spec_exchange.py::TestPullSteps::test_repair_before_the_merge

### 6.3 New entries (contract)

- tests/test_pools_more.py::TestPullEntries::test_key_taken
- tests/test_pools_more.py::TestPullEntries::test_pull_pool_key
- tests/test_pools_more.py::TestPullEntries::test_copy_mode
- tests/test_spec_exchange.py::TestPullNew::test_fields_without_ids
- tests/test_spec_exchange.py::TestPullNew::test_suffix_without_case

### 6.4 Files of a pull

- tests/test_pools.py::TestPull::test_new_pool_file
- tests/test_pools_more.py::TestPullEntries::test_copy_mode
- tests/test_pools_more.py::TestPullEntries::test_shallow_links
- tests/test_pools.py::TestShallow::test_pull_links_to_pool_files
- tests/test_auto_push.py::TestShallowSharedLinks::test_pull_removes_the_links_the_pool_removed
- tests/test_exchanges.py::TestShallowWithOther::test_pull
- tests/test_spec_exchange.py::TestPullFiles::test_files_kept_where_they_are
- tests/test_spec_exchange.py::TestPullFiles::test_move_mode_copies
- tests/test_spec_exchange.py::TestPullFiles::test_without_files_directory

### 7.1 Selection

- tests/test_pools.py::TestPush::test_shared_entries_only
- tests/test_pools.py::TestPush::test_new_entry
- tests/test_auto_push.py::TestRemovedFromThePool::test_push
- tests/test_auto_push.py::TestRemovedFromThePool::test_push_key_adds_it_back
- tests/test_auto_push.py::TestSharedWithoutRecord::test_push
- tests/test_spec_exchange.py::TestPushSelection::test_all_adds_back_removed
- tests/test_spec_exchange.py::TestPushSelection::test_list_push

### 7.2 Steps

- tests/test_pools.py::TestPush::test_changes
- tests/test_pools.py::TestPush::test_push_keeps_a_pool_change
- tests/test_pools.py::TestPush::test_existing_pool_entry
- tests/test_pools.py::TestPush::test_pool_only_fields_come_with_the_next_pull
- tests/test_pools.py::TestPush::test_distinct_merged
- tests/test_unreadable.py::TestUnreadable::test_push_refused
- tests/test_auto_push.py::TestShallowSharedLinks::test_push_does_not_add_back_the_links_the_pool_removed
- tests/test_exchanges.py::TestShallowWithOther::test_push
- tests/test_spec_exchange.py::TestPushSteps::test_new_file_copied_into_the_pool

### 7.3 Entries new to the pool (contract)

- tests/test_pools.py::TestPush::test_new_entry
- tests/test_pools.py::TestPush::test_pool_name_template
- tests/test_pools.py::TestShallow::test_push_never_writes_empty_entry
- tests/test_auto_push.py::TestShallowSharedLinks::test_add_link_mode_entry_new_to_the_pool
- tests/test_spec_exchange.py::TestPushNew::test_empty_entry
- tests/test_spec_exchange.py::TestPushNew::test_key_suffix_in_the_pool
- tests/test_spec_exchange.py::TestPushNew::test_no_key_template_key
- tests/test_spec_exchange.py::TestPushNew::test_fields_without_ids

### 8. `papers sync`

- tests/test_pools_more.py::TestSync::test_pull_then_push
- tests/test_pools_more.py::TestSync::test_nothing_shared
- tests/test_pools_more.py::TestSync::test_not_found_only_for_keys_given
- tests/test_pools_more.py::TestSync::test_conflict_stops_before_push
- tests/test_pools_more.py::TestSync::test_selection
- tests/test_spec_exchange.py::TestSync::test_conflict_exit_status

### 9. `papers pull --check`

- tests/test_pools.py::TestPull::test_check_and_status
- tests/test_pools_more.py::TestPullCheck::test_not_found_in_pool
- tests/test_pools_more.py::TestPullCheck::test_not_pulled_yet
- tests/test_pools_more.py::TestPullCheck::test_new_pool_file
- tests/test_pools_more.py::TestPullCheck::test_conflict_count
- tests/test_auto_push.py::TestRemovals::test_pull_check_lists_a_removal
- tests/test_auto_push.py::TestSharedWithoutRecord::test_pull_check
- tests/test_spec_exchange.py::TestPullCheck::test_nothing_written
- tests/test_spec_exchange.py::TestPullCheck::test_fields_sorted_and_conflicts
- tests/test_spec_exchange.py::TestPullCheck::test_nothing_to_pull

### 10. One-time exchanges: `--pool PATH`

- tests/test_pools_onetime.py::TestOneTime::test_records_for_each_library
- tests/test_pools_more.py::TestPullEntries::test_other_pool
- tests/test_exchanges.py::TestAddPool::test_self_contained
- tests/test_exchanges.py::TestAddPool::test_new_entry_is_not_sent
- tests/test_exchanges.py::TestAddPool::test_shallow
- tests/test_exchanges.py::TestShallowWithOther::test_pull
- tests/test_exchanges.py::TestShallowWithOther::test_push
- tests/test_pools.py::TestAdd::test_auto_push_ignored_without_pool

### 12.1 What is pushed (contract)

- tests/test_auto_push.py::TestAutoPush::test_tag
- tests/test_auto_push.py::TestAutoPush::test_list_add_tag
- tests/test_auto_push.py::TestAutoPush::test_edit
- tests/test_auto_push.py::TestAutoPush::test_edit_key
- tests/test_auto_push.py::TestAutoPush::test_check_duplicates
- tests/test_auto_push.py::TestAutoPush::test_add_new_entry
- tests/test_auto_push.py::TestAutoPush::test_file_attach_and_detach
- tests/test_auto_push.py::TestAutoPush::test_only_the_entries_changed
- tests/test_auto_push.py::TestAutoPush::test_entry_not_shared_is_not_pushed
- tests/test_auto_push.py::TestAutoPush::test_rm_is_not_pushed
- tests/test_auto_push.py::TestAutoPush::test_conflict_does_not_stop_the_command
- tests/test_auto_push.py::TestAutoPushOff::test_nothing_pushed
- tests/test_auto_push.py::TestShallowAutoPush::test_add_new_entry_goes_to_the_pool
- tests/test_auto_push.py::TestShallowAutoPush::test_changes_not_pushed
- tests/test_auto_push.py::TestShallowAutoPush::test_changes_pushed_with_auto_push
- tests/test_auto_push.py::TestRemovedFromThePool::test_auto_push
- tests/test_pools.py::TestAdd::test_auto_push_ignored_without_pool
- tests/test_undo_pool.py::TestUndoPoolAutoPush::test_undo_pushes_what_a_step_did_not
- tests/test_spec_exchange.py::TestPoolRules::test_configured_pool_with_a_pool_auto_push_warns
- tests/test_spec_exchange.py::TestAutoPush::test_pool_unusable_warns
- tests/test_spec_exchange.py::TestAutoPush::test_renamed_entry_is_not_new

### 12.3 Link updates (contract)

- tests/test_auto_push.py::TestShallowFileLinks::test_attach
- tests/test_auto_push.py::TestShallowFileLinks::test_rename
- tests/test_auto_push.py::TestShallowFileLinks::test_detach
- tests/test_auto_push.py::TestShallowFileLinks::test_rm
- tests/test_auto_push.py::TestShallowFileLinks::test_mv
- tests/test_auto_push.py::TestShallowFileLinks::test_check_fix
- tests/test_auto_push.py::TestShallowFileLinks::test_entry_not_shared_in_the_pool
- tests/test_auto_push.py::TestShallowFileLinks::test_entry_not_in_the_pool
- tests/test_auto_push.py::TestShallowFileLinks::test_local_library_is_unaffected
- tests/test_auto_push.py::TestShallowSharedLinks::test_attach_link_mode
- tests/test_auto_push.py::TestShallowSharedLinks::test_attach_move_mode
- tests/test_auto_push.py::TestShallowSharedLinks::test_loaded_link_not_sent
- tests/test_spec_exchange.py::TestLinkUpdates::test_record_file_field

### 13.1 Lookup (contract for what is matched)

- tests/test_pools.py::TestAdd::test_bibtex
- tests/test_pools.py::TestAdd::test_doi
- tests/test_pools.py::TestAdd::test_doi_with_fields
- tests/test_pools.py::TestAdd::test_key
- tests/test_pools.py::TestAdd::test_key_not_found
- tests/test_pools.py::TestAdd::test_no_empty_entry
- tests/test_pools.py::TestAdd::test_pdf_same_content
- tests/test_pools.py::TestAdd::test_pdf_same_content_move_mode
- tests/test_pools.py::TestAdd::test_attachment_different_content_move_mode
- tests/test_pools.py::TestAdd::test_pdf_doi_in_text
- tests/test_pools.py::TestAdd::test_copy_mode
- tests/test_pools.py::TestAdd::test_move_mode_never_moves_pool_files
- tests/test_pools.py::TestAdd::test_library_name_template
- tests/test_pools.py::TestAdd::test_no_pool
- tests/test_pools.py::TestShallow::test_add_from_pool_links_to_pool_file
- tests/test_auto_push.py::TestOwnFields::test_add_from_the_pool_without_its_ids
- tests/test_exchanges.py::TestAddPool::test_self_contained
- tests/test_spec_exchange.py::TestAddLookup::test_bibtex_entry_keeps_its_key_and_fields
- tests/test_spec_exchange.py::TestAddLookup::test_pdf_metadata_doi

### 13.2 After the lookup

- tests/test_auto_push.py::TestShallowAutoPush::test_add_new_entry_goes_to_the_pool
- tests/test_exchanges.py::TestAddPool::test_shallow
- tests/test_exchanges.py::TestAddPool::test_new_entry_is_not_sent
- tests/test_pools.py::TestStatus::test_after_add_from_pool
- tests/test_pools.py::TestAdd::test_key

### 14.1 The pool line

- tests/test_pools.py::TestStatus::test_status
- tests/test_pools.py::TestStatus::test_status_not_pulled_in_full
- tests/test_pools.py::TestStatus::test_pool_changed
- tests/test_pools.py::TestStatus::test_library_changed
- tests/test_pools.py::TestStatus::test_both_changed
- tests/test_pools.py::TestStatus::test_missing_pool
- tests/test_pools.py::TestConfigPoolSelfContained::test_config_pool_not_the_library_itself
- tests/test_spec_exchange.py::TestStatusLine::test_not_a_library

### 14.2 The time check (`pull --check`)

- tests/test_pools.py::TestPull::test_check_and_status
- tests/test_pools.py::TestStatus::test_status_not_pulled_in_full
- tests/test_pools.py::TestStatus::test_after_add_from_pool
- tests/test_spec_exchange.py::TestPullCheck::test_not_pulled_from_yet

### 14.3 The content comparison (contract for the result)

- tests/test_pools.py::TestStatus::test_pool_changed
- tests/test_pools.py::TestStatus::test_library_changed
- tests/test_pools.py::TestStatus::test_both_changed
- tests/test_pools.py::TestStatus::test_same_change_on_both_sides
- tests/test_pools.py::TestStatus::test_fast_path_after_a_touch
- tests/test_pools.py::TestStatus::test_entry_type_changed
- tests/test_pools.py::TestStatus::test_entry_removed_from_the_pool
- tests/test_pools.py::TestStatus::test_other_entries_of_the_pool
- tests/test_pools.py::TestPull::test_conflict_skip
- tests/test_pools.py::TestShallow::test_status_sees_repaired_links
- tests/test_spec_exchange.py::TestStatusComparison::test_entry_without_record_not_compared
- tests/test_spec_exchange.py::TestStatusComparison::test_link_removed_by_the_pool
- tests/test_spec_exchange.py::TestStatusComparison::test_writes_nothing_in_the_library

### 14.4 The fast comparison by pieces (free; contract for the file if written)

- tests/test_pools.py::TestStatus::test_fast_path
- tests/test_pools.py::TestStatus::test_fast_path_after_a_touch
- tests/test_pools.py::TestStatus::test_entry_removed_from_the_pool
- tests/test_spec_exchange.py::TestExchangesJson::test_exact_content
- tests/test_spec_exchange.py::TestExchangesJson::test_unreadable_file_means_not_known

### 15.1 The pool's files directory

- tests/test_pools.py::TestShallow::test_add_places_files_in_pool
- tests/test_pools.py::TestShallow::test_file_attach_places_files_in_pool
- tests/test_pools.py::TestShallow::test_file_rename_places_files_in_pool
- tests/test_exchanges.py::TestShallowWithOther::test_pull
- tests/test_exchanges.py::TestAddPool::test_shallow

### 15.2 Links that the pool removed (contract)

- tests/test_auto_push.py::TestShallowSharedLinks::test_pull_removes_the_links_the_pool_removed
- tests/test_auto_push.py::TestShallowSharedLinks::test_push_does_not_add_back_the_links_the_pool_removed
- tests/test_auto_push.py::TestShallowSharedLinks::test_sync_removes_the_links_the_pool_removed
- tests/test_auto_push.py::TestShallowSharedLinks::test_pull_without_recorded_links_removes_nothing
- tests/test_auto_push.py::TestShallowSharedLinks::test_record_of_development_builds
- tests/test_pools.py::TestShallow::test_link_removed_in_pool
- tests/test_spec_exchange.py::TestStatusComparison::test_link_removed_by_the_pool

### 15.3 Repair of broken links to pool files (contract for the choice)

- tests/test_pools.py::TestShallow::test_broken_link_repaired_on_load
- tests/test_pools.py::TestShallow::test_status_sees_repaired_links
- tests/test_pools.py::TestShallow::test_file_check_fix
- tests/test_pools_more.py::TestExchange::test_repair_links_without_pool_entry_or_file
- tests/test_file_relink.py::TestPoolRelink::test_same_name
- tests/test_file_relink.py::TestPoolRelink::test_label_then_pair
- tests/test_file_relink.py::TestPoolRelink::test_pairing_ambiguous
- tests/test_file_relink.py::TestPoolRelink::test_label_ambiguous
- tests/test_file_relink.py::TestPoolRelink::test_no_guess
- tests/test_spec_exchange.py::TestRepair::test_first_link_takes_the_rest
- tests/test_spec_exchange.py::TestRepair::test_saved_at_the_next_save

### 15.4 Changing the pool

- tests/test_pools.py::TestConfigPool::test_pool_none
- tests/test_pools.py::TestConfigPool::test_other_pool
- tests/test_pools.py::TestConfigPoolSelfContained::test_becomes_shallow
- tests/test_pools_onetime.py::TestOneTime::test_config_pool_finds_the_records
- tests/test_pools_more.py::TestPoolIdentifier::test_library_moved

### 16. The history (outline)

- tests/test_pools.py::TestOrigin::test_history
- tests/test_undo_pool.py::TestUndoPool::test_add_then_undo_redo
- tests/test_undo_pool.py::TestUndoPool::test_add_then_undo_library_only
- tests/test_undo_pool.py::TestUndoPool::test_pool_changed_since
- tests/test_undo_pool.py::TestUndoPool::test_redo_after_the_pool_moved_on
- tests/test_undo_pool.py::TestUndoPool::test_undo_after_push
- tests/test_undo_pool.py::TestUndoPool::test_undo_after_pull
- tests/test_undo_pool.py::TestUndoPool::test_undo_restores_distinct
- tests/test_undo_pool.py::TestUndoPoolAutoPush::test_undo_pushes_what_a_step_did_not
- tests/test_undo_pool.py::TestSeveralSavesOfThePool::test_undo (the rules themselves: history.md).

## history.md

### 1. What the history is

- tests/test_history.py::TestPlaces::test_moved_library_continues
- tests/test_history.py::TestPlaces::test_copied_library_branches.

### 2.1 Location

- tests/test_spec_history.py::TestLocation::test_default_location
- tests/test_spec_history.py::TestLocation::test_relative_history_dir
- tests/test_spec_history.py::TestLocation::test_home
- tests/test_spec_history.py::TestLocation::test_nothing_created_without_a_change
- tests/test_config_unit.py::TestPathsOfSettings::test_relative_to_the_global_configuration
- tests/test_config_unit.py::TestLibraryId::test_machine_settings_not_read_from_a_library
- tests/test_library_cmds.py::TestConfigCmd::test_machine_settings
- tests/test_library_cmds.py::TestConfigCmd::test_global_path_relative_to_current_directory
- tests/test_history.py::TestSeparate::test_dry_run_writes_nothing.

### 2.2 Layout

- tests/test_spec_history.py::TestLayout::test_layout
- tests/test_spec_history.py::TestLayout::test_project_id
- tests/test_history.py::TestStates::test_identifier.

### 2.3 Objects: pieces of text

- tests/test_spec_history.py::TestObjects::test_example
- tests/test_spec_history.py::TestObjects::test_piece_max
- tests/test_spec_history.py::TestObjects::test_segments
- tests/test_spec_history.py::TestObjects::test_object_file
- tests/test_spec_history.py::TestObjects::test_any_zlib_stream
- tests/test_spec_history.py::TestObjects::test_existing_object_refreshed
- tests/test_spec_history.py::TestObjects::test_tmp_files_are_not_objects
- tests/test_spec_history.py::TestObjectsOfALibrary::test_bytes_of_the_file
- tests/test_spec_history.py::TestObjectsOfALibrary::test_missing_piece
- tests/test_history.py::TestPieces::test_byte_for_byte
- tests/test_history.py::TestPieces::test_pieces_of_entries
- tests/test_history.py::TestPieces::test_shared_pieces
- tests/test_history.py::TestPieces::test_missing_piece.

### 2.4 File objects: deleted files

- tests/test_spec_history.py::TestFileObjects::test_extension_as_written
- tests/test_spec_history.py::TestFileObjects::test_lookup_by_checksum
- tests/test_spec_history.py::TestFileObjects::test_stored_again
- tests/test_spec_history.py::TestFileObjects::test_shared_by_the_projects
- tests/test_history.py::TestPieces::test_files.

### 2.5 States and their identifiers

- tests/test_history.py::TestStates::test_tree
- tests/test_history.py::TestStates::test_state_identifier
- tests/test_history.py::TestStates::test_upgrade_numbered_states
- tests/test_history.py::TestStoredNames::test_known_state_id
- tests/test_undo_pool.py::TestNumberedStatesOfTwoStores::test_library_upgraded_first
- tests/test_undo_pool.py::TestNumberedStatesOfTwoStores::test_pool_upgraded_first
- tests/test_undo.py::TestTimeTravel::test_unknown_state
- tests/test_spec_history.py::TestStates::test_written_once
- tests/test_spec_history.py::TestStates::test_other_files_ignored
- tests/test_spec_history.py::TestStates::test_naming
- tests/test_spec_history.py::TestStates::test_several
- tests/test_spec_history.py::TestStates::test_json
- tests/test_spec_history.py::TestStates::test_numbers_json.

### 2.6 Separate stores

- tests/test_history.py::TestSeparate::test_own_store
- tests/test_history.py::TestSeparate::test_size_of_its_own
- tests/test_spec_history.py::TestSeparateStores::test_machine_setting
- tests/test_spec_history.py::TestSeparateStores::test_bibtex_without_library
- tests/test_spec_history.py::TestSeparateStores::test_change_of_the_setting.

### 2.7 `heads.json`

- tests/test_spec_history.py::TestHeads::test_format
- tests/test_spec_history.py::TestHeads::test_missing_states
- tests/test_spec_history.py::TestHeads::test_unreadable
- tests/test_history.py::TestStates::test_places.

### 2.8 Writing order

- tests/test_spec_history.py::TestWritingOrder::test_order.

### 3.1 Keys

- tests/test_spec_history.py::TestKeys::test_keys
- tests/test_spec_history.py::TestKeys::test_without_kind
- tests/test_spec_history.py::TestKeys::test_unknown_keys_kept
- tests/test_history.py::TestStates::test_state_identifier.

### 3.2 Kinds and messages

- tests/test_spec_history.py::TestKinds::test_kinds
- tests/test_history.py::TestHistoryCommand::test_list.

### 3.3 The kept `.papers/` files

- tests/test_spec_history.py::TestKeptFiles::test_names
- tests/test_spec_history.py::TestKeptFiles::test_library_directory
- tests/test_history.py::TestStoredNames::test_known_state_id
- tests/test_history.py::TestStoredNames::test_windows_separators
- tests/test_library_folder.py::LibraryFolderTest::test_undo_across_the_move
- tests/test_undo_pool.py::TestUndoPool::test_undo_restores_distinct.

### 3.4 `deleted`

- tests/test_spec_history.py::TestDeleted::test_sorted_without_repeats
- tests/test_journal.py::TestDeleted::test_rm_undo_restores_from_the_history
- tests/test_file_cmd.py::TestFixFromHistory::test_restored_file_kept_by_its_step.

### 4. File operations

- tests/test_spec_history.py::TestFileOperations::test_trashed
- tests/test_spec_history.py::TestFileOperations::test_moved
- tests/test_spec_history.py::TestFileOperations::test_paths_absolute
- tests/test_spec_history.py::TestFileOperations::test_copied
- tests/test_spec_history.py::TestFileOperations::test_relative_to_the_copy
- tests/test_history.py::TestDownloads::test_add_move_undo
- tests/test_history.py::TestStoredNames::test_windows_separators
- tests/test_journal.py::TestSeveralSteps::test_operations_in_the_state
- tests/test_journal.py::TestDeleted::test_identical_copy_not_kept.

### 5.1 The place and the project of a library

- tests/test_spec_history.py::TestRecording::test_id_created_at_the_first_state
- tests/test_spec_history.py::TestSeparateStores::test_bibtex_without_library
- tests/test_history.py::TestPlaces::test_no_trace_before_a_change
- tests/test_history.py::TestPlaces::test_export_has_its_own_history
- tests/test_history.py::TestSeparate::test_dry_run_writes_nothing.

### 5.2 The head of a place, and changes made outside papers

- tests/test_spec_history.py::TestRecording::test_outside_state_files_from_disk
- tests/test_undo_pool.py::TestUndoPool::test_undo_across_an_outside_change_of_the_origin_records
- tests/test_undo.py::TestOutsideChanges::test_not_dropped_by_undo
- tests/test_undo.py::TestOutsideChanges::test_undo_right_after_an_outside_change
- tests/test_spec_history.py::TestKinds::test_kinds
- tests/test_history.py::TestStates::test_places
- tests/test_history.py::TestPlaces::test_moved_library_continues
- tests/test_history.py::TestPlaces::test_copied_library_branches.

### 5.3 The library before the command

- tests/test_spec_history.py::TestRecording::test_library_before_the_command
- tests/test_history.py::TestPlaces::test_no_trace_before_a_change.

### 5.4 The state after a save

- tests/test_spec_history.py::TestRecording::test_no_state_for_an_identical_save
- tests/test_spec_history.py::TestRecording::test_command_after_undo_starts_a_branch
- tests/test_spec_history.py::TestPoolLink::test_link
- tests/test_journal.py::TestRefusedSave::test_files_put_back
- tests/test_journal.py::TestRefusedSave::test_deleted_files_put_back
- tests/test_journal.py::TestRefusedSave::test_rollback
- tests/test_undo.py::TestTimeTravel::test_undo_then_change_branches
- tests/test_journal.py::TestSeveralSteps::test_operations_in_the_state.

### 5.5 Operations after the save

- tests/test_spec_history.py::TestRecording::test_operations_after_the_head_moved
- tests/test_journal.py::TestDeleted::test_rm_undo_restores_from_the_history
- tests/test_journal.py::TestDeleted::test_operations_after_a_save_without_state
- tests/test_journal.py::TestCommandsThatDoNotSave::test_file_clean_undo
- tests/test_journal.py::TestCommandsThatDoNotSave::test_interrupted
- tests/test_journal.py::TestSeveralSteps::test_add_then_delete_several_steps.

### 5.6 Deleted files

- tests/test_journal.py::TestDeleted::test_rm_undo_restores_from_the_history
- tests/test_journal.py::TestDeleted::test_keep_deleted_files_false
- tests/test_journal.py::TestDeleted::test_identical_copy_not_kept
- tests/test_journal.py::TestGuard::test_more_than_the_history_keeps_without_terminal
- tests/test_journal.py::TestGuard::test_more_than_the_history_keeps_confirmed
- tests/test_journal.py::TestGuard::test_answer_no
- tests/test_journal.py::TestGuard::test_yes
- tests/test_journal.py::TestGuard::test_lesser_case_recent_states
- tests/test_journal.py::TestGuard::test_no_limit.

### 5.7 Summary

- those of 5.1 to 5.6, 6.2 and 7.1 (the table sums them up).

### 6.1 The path between two states

- tests/test_history.py::TestStates::test_tree.

### 6.2 The commands

- tests/test_spec_history.py::TestCommands::test_no_state_added
- tests/test_spec_history.py::TestCommands::test_redo_list_of_undo
- tests/test_spec_history.py::TestCommands::test_redo_after_an_outside_change
- tests/test_spec_history.py::TestCommands::test_restore_redo_list
- tests/test_spec_history.py::TestCommands::test_nothing_to_restore
- tests/test_undo.py::TestTimeTravel::test_undo_redo
- tests/test_undo.py::TestTimeTravel::test_nothing_to_undo
- tests/test_undo.py::TestTimeTravel::test_undo_then_change_branches
- tests/test_undo.py::TestTimeTravel::test_dry_run
- tests/test_undo.py::TestOutsideChanges::test_undo_right_after_an_outside_change
- tests/test_undo.py::TestOutsideChanges::test_restore_drops_the_outside_change
- tests/test_journal.py::TestSeveralSteps::test_restore_state
- tests/test_undo_pool.py::TestUndoPool::test_restore_ref_restores_origin.

### 6.3 Going to a state

- tests/test_spec_history.py::TestGoingToAState::test_kept_files_written_and_removed
- tests/test_spec_history.py::TestObjectsOfALibrary::test_bytes_of_the_file
- tests/test_undo.py::TestTimeTravel::test_undo_redo
- tests/test_undo_pool.py::TestUndoPool::test_add_then_undo_redo
- tests/test_undo_pool.py::TestUndoPool::test_undo_restores_distinct
- tests/test_journal.py::TestChecksums::test_found_by_checksum.

### 6.4 Restoring the files

- tests/test_journal.py::TestOneStep::test_rename_undo_redo
- tests/test_journal.py::TestOneStep::test_copy_removed_by_undo
- tests/test_journal.py::TestOneStep::test_file_changed_since
- tests/test_journal.py::TestOneStep::test_place_taken
- tests/test_journal.py::TestOneStep::test_only_the_last_command
- tests/test_journal.py::TestOneStep::test_file_mv
- tests/test_journal.py::TestOneStep::test_deleted_file_reported
- tests/test_journal.py::TestSeveralSteps::test_one_step_at_a_time
- tests/test_journal.py::TestSeveralSteps::test_several_steps
- tests/test_journal.py::TestSeveralSteps::test_chain_of_moves
- tests/test_journal.py::TestSeveralSteps::test_external_file_only_unlinked
- tests/test_journal.py::TestSeveralSteps::test_add_moved_from_outside
- tests/test_journal.py::TestSeveralSteps::test_add_then_delete_several_steps
- tests/test_journal.py::TestSeveralSteps::test_add_copied_from_outside
- tests/test_journal.py::TestChecksums::test_found_by_checksum
- tests/test_journal.py::TestShallow::test_moved_back
- tests/test_journal.py::TestShallow::test_copied_back
- tests/test_journal.py::TestDeleted::test_history_emptied
- tests/test_journal.py::TestDeleted::test_identical_copy_not_kept
- tests/test_journal.py::TestDeleted::test_redo_with_keep_deleted_files_false
- tests/test_journal.py::TestCommandsThatDoNotSave::test_file_clean_undo
- tests/test_file_cmd.py::TestFixFromHistory::test_restore
- tests/test_file_cmd.py::TestFixFromHistory::test_restored_file_after_history_dir_change.

### 6.6 Files brought back by `papers file check` and `fix`

- tests/test_file_cmd.py::TestFixFromHistory::test_restore
- tests/test_file_cmd.py::TestFixFromHistory::test_by_checksum
- tests/test_file_cmd.py::TestFixFromHistory::test_restored_file_kept_by_its_step
- tests/test_file_cmd.py::TestFixFromHistory::test_restored_file_after_history_dir_change.

### 7.1 The link

- tests/test_spec_history.py::TestPoolLink::test_link
- tests/test_undo_pool.py::TestSeveralSavesOfThePool::test_undo
- tests/test_revert.py::TestRevertShallow::test_pool_line.

### 7.2 Finding the pool steps

- tests/test_spec_history.py::TestPoolLink::test_pool_not_found
- tests/test_undo_pool.py::TestUndoPool::test_pool_changed_since
- tests/test_undo_pool.py::TestUndoPool::test_pool_changed_since_elsewhere
- tests/test_undo_pool.py::TestUndoPool::test_redo_after_the_pool_moved_on
- tests/test_undo_pool.py::TestUndoPool::test_pool_changed_outside_papers
- tests/test_undo_pool.py::TestUndoPool::test_pool_undone_first
- tests/test_undo_pool.py::TestSeveralSavesOfThePool::test_undo
- tests/test_undo_pool.py::TestNumberedStatesOfTwoStores::test_library_upgraded_first.

### 7.3 Moving the pools

- tests/test_undo_pool.py::TestUndoPool::test_add_then_undo_redo
- tests/test_undo_pool.py::TestUndoPool::test_pool_changed_since
- tests/test_undo_pool.py::TestUndoPool::test_pool_changed_since_elsewhere
- tests/test_undo_pool.py::TestUndoPool::test_redo_after_the_pool_moved_on
- tests/test_undo_pool.py::TestUndoPool::test_undo_after_push
- tests/test_undo_pool.py::TestUndoPoolAutoPush::test_add_then_undo_redo.

### 7.4 Order

- tests/test_journal.py::TestShallow::test_moved_back
- tests/test_journal.py::TestShallow::test_copied_back
- tests/test_undo_pool.py::TestUndoFileRmShallow::test_undo_file_rm.

### 7.5 `--library-only`, and commands run in the pool

- tests/test_undo_pool.py::TestUndoPool::test_add_then_undo_library_only
- tests/test_undo_pool.py::TestUndoPool::test_undo_after_push_library_only
- tests/test_undo_pool.py::TestUndoPool::test_pool_undo_redo
- tests/test_undo_pool.py::TestUndoPool::test_restore_ref_restores_origin
- tests/test_journal.py::TestShallow::test_copied_back.

### 7.6 Auto-push after undo and redo

- tests/test_undo_pool.py::TestUndoPoolAutoPush::test_undo_pushes_what_a_step_did_not
- tests/test_undo_pool.py::TestUndoPoolAutoPush::test_undo_without_anything_to_push.

### 8. Revert: `papers history --revert STEP`

- tests/test_spec_history.py::TestRevert::test_errors
- tests/test_revert.py::TestRevertEntries::test_errors.

### 8.1 The entries step N changed

- those of 8.2.

### 8.2 Rules per entry

- tests/test_revert.py::TestRevertEntries::test_tags_one_by_one
- tests/test_revert.py::TestRevertEntries::test_tag_removed_comes_back
- tests/test_revert.py::TestRevertEntries::test_field
- tests/test_revert.py::TestRevertEntries::test_conflict
- tests/test_revert.py::TestRevertEntries::test_skip
- tests/test_revert.py::TestRevertEntries::test_added_entry
- tests/test_revert.py::TestRevertEntries::test_added_entry_changed_since
- tests/test_revert.py::TestRevertEntries::test_removed_entry
- tests/test_revert.py::TestRevertEntries::test_removed_entry_whose_key_is_taken
- tests/test_revert.py::TestRevertEntries::test_key.

### 8.3 Files, `distinct.json`, origin records

- tests/test_revert.py::TestRevertEntries::test_distinct
- tests/test_revert.py::TestRevertEntries::test_dry_run
- tests/test_revert.py::TestRevertFiles::test_added_with_file
- tests/test_revert.py::TestRevertFiles::test_removed_with_file
- tests/test_spec_history.py::TestRevert::test_origin_records_unchanged.

### 8.4 The state

- tests/test_spec_history.py::TestRevert::test_state
- tests/test_revert.py::TestRevertEntries::test_tags_one_by_one
- tests/test_revert.py::TestRevertShallow::test_pool_line.

### 8.5 Doing a step again

- tests/test_undo_pool.py::TestUndoPool::test_redo_after_the_pool_moved_on.

### 9.1 The limit

- tests/test_spec_history.py::TestSize::test_what_counts
- tests/test_spec_history.py::TestSizeOfALibrary::test_machine_value_for_the_shared_store
- tests/test_spec_history.py::TestSizeOfALibrary::test_separate_store_falls_back_to_the_machine
- tests/test_history.py::TestSeparate::test_size_of_its_own
- tests/test_history.py::TestSeparate::test_shared_store_in_a_folder_named_separate.

### 9.2 Pruning

- tests/test_spec_history.py::TestPruning::test_no_limit_frees_unreferenced_objects
- tests/test_spec_history.py::TestPruning::test_order_by_time_then_identifier
- tests/test_spec_history.py::TestPruning::test_heads_of_all_projects_protected
- tests/test_history.py::TestPrune::test_oldest_states_first
- tests/test_history.py::TestPrune::test_recent_objects_kept
- tests/test_history.py::TestPrune::test_objects_of_dropped_states
- tests/test_history.py::TestPrune::test_object_used_again_kept
- tests/test_history.py::TestPrune::test_recent_orphans_do_not_push_states_out
- tests/test_history.py::TestPrune::test_files_to_the_discard
- tests/test_history.py::TestPrune::test_extra
- tests/test_journal.py::TestCyclicalRemoval::test_last_three_kept.

### 9.3 `papers history --remove [ID]`

- tests/test_spec_history.py::TestRemove::test_last_place_prunes
- tests/test_spec_history.py::TestRemove::test_by_id
- tests/test_spec_history.py::TestRemove::test_no_project
- tests/test_history.py::TestHistoryCommand::test_all_and_remove
- tests/test_history.py::TestHistoryCommand::test_remove_keeps_the_history_of_a_copy
- tests/test_history.py::TestHistoryCommand::test_remove_without_terminal.

### 9.4 `papers history --drop-files STEP|PATH`

- tests/test_spec_history.py::TestDropFiles::test_file_kept_by_another_project
- tests/test_spec_history.py::TestKeys::test_unknown_keys_kept
- tests/test_journal.py::TestDropFiles::test_size_in_the_list
- tests/test_journal.py::TestDropFiles::test_drop_by_step
- tests/test_journal.py::TestDropFiles::test_drop_by_path
- tests/test_journal.py::TestDropFiles::test_confirmation
- tests/test_journal.py::TestDropFiles::test_unknown_step.

### 9.5 `keep-deleted-files`

- tests/test_journal.py::TestDeleted::test_keep_deleted_files_false
- tests/test_journal.py::TestDeleted::test_redo_with_keep_deleted_files_false.

### 10. `.papers/files.json`

- tests/test_spec_history.py::TestFilesJson::test_format
- tests/test_spec_history.py::TestFilesJsonKeys::test_written_and_read_with_slash
- tests/test_spec_history.py::TestFilesJson::test_absolute
- tests/test_spec_history.py::TestFilesJson::test_deleted_without_checksums
- tests/test_spec_history.py::TestFilesJson::test_relative_to_the_bibtex
- tests/test_journal.py::TestChecksums::test_written_by_the_commands
- tests/test_journal.py::TestChecksums::test_setting_off
- tests/test_journal.py::TestChecksums::test_command
- tests/test_journal.py::TestChecksums::test_found_by_checksum
- tests/test_undo.py::TestUndoNoInstall::test_undo.

### 11. The parse cache

- tests/test_parsecache.py::TestParseCache::test_cases
- tests/test_parsecache.py::TestParseCache::test_files_of_the_tests
- tests/test_parsecache.py::TestParseCache::test_only_changed_pieces_are_split
- tests/test_parsecache.py::TestParseCache::test_not_cached_when_a_block_fails
- tests/test_parsecache.py::TestParseCache::test_prune
- tests/test_parsecache.py::TestParseCache::test_damaged_cache.
