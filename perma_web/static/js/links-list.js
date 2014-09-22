$(function(){
    var table = $('.vested-table');

    // helpers
    function postJSON(url, data, callback, failureCallback){
        return $.ajax({
			url: url,
			type: "POST",
			dataType: 'json',
			data: data,
			success: callback,
            traditional: true // use Django-style array serialization
		}).fail(
            failureCallback || function(jqXHR) {
                informUser(jqXHR.status == 400 && jqXHR.responseText ? jqXHR.responseText : "Error " + jqXHR.status, 'danger');
            }
        );
    }

    // new folder form
    $('#new_folder_show, #new_folder_cancel').on('click', function(){
        $('#new_folder_container, #new_folder_name_container').toggle("fast");
    });
    $('#new_folder_name').on('keyup', function(){
        if(this.value)
            $("#new_folder_submit").removeAttr("disabled");
        else
            $("#new_folder_submit").attr("disabled", true);
    });

    // link details
    var notesSaveNeeded = false,
        lastNotesSaveTime = 0,
        saveBufferSeconds = 3;
    $('.tab-pane').on('click', '.linky-details-link a', function(){
        // handle details link to hide/show link details
        $(this).closest('tr').next('.link-details').toggle();
        return false;

    }).on('input propertychange', '.link-details textarea', function(){
        // save changes to link notes
        var textarea = $(this),
            linkID = textarea.closest('tr').prev('.link-row').attr('link_id'),
            statusArea = textarea.prevAll('.notes-save-status');
        statusArea.html('saving ...');
        notesSaveNeeded = true;

        // use a setTimeout so notes are only saved once every few seconds
        setTimeout(function(){
            if(notesSaveNeeded){
                postJSON(
                    '#',
                    {action:'save_notes',link_id:linkID,notes:textarea.val()},
                    function(data){
                        statusArea.html('saved.')
                    }
                );
            }
            lastNotesSaveTime = new Date().getTime();
        }, Math.max(saveBufferSeconds*1000 - (new Date().getTime() - lastNotesSaveTime), 0));
    });


    // manage title save
    var titleSaveNeeded = false,
        lastTitleSaveTime = 0;

    $('.linky-abbr-title input').on('input propertychange', function(){
        // save changes to title fields
        var textarea = $(this),
            linkID = textarea.closest('tr').attr('link_id'),
            statusArea = textarea.nextAll('.title-save-status');
        statusArea.html('saving ...');
        titleSaveNeeded = true;

        // use a setTimeout so titles are only saved once every few seconds
        setTimeout(function(){
            if(titleSaveNeeded){
                postJSON(
                    '#',
                    {action: 'save_title', link_id: linkID, title: textarea.val()},
                    function(data){
                        statusArea.html('saved.')
                    }
                );
            }
            lastTitleSaveTime = new Date().getTime();
        }, Math.max(saveBufferSeconds*1000 - (new Date().getTime() - lastTitleSaveTime), 0));
    });

    $('.tab-pane').on('click', '.folder-row a.delete', function(){
        // folder delete
        var td = $(this).parent().parent(),
        aTag = td.find('a');
        if(confirm("Really delete folder?")){
            postJSON(
                aTag.attr('href'), // subfolder url
                {action:'delete_folder'},
                function(data){
                    if(data.success){
                        td.remove();
                    }else{
                        alert(data.error);
                    }
                }
            );
        }
        return false;

    }).on('click', '.folder-row a.rename', function(){
        // folder rename - show form
        $(this).closest('.tool-block').hide();
        var aTag = $(this).parent().parent().find('.folder-name a');
        aTag.hide().after($('#form_templates .rename-folder-form').clone().hide()).next().show();
        $(this).parent().parent().find('input[name="folder_name"]').val(aTag.text());
        return false;

    }).on('click', '.folder-row input[name="rename_folder_cancel"]', function(){
        // folder rename - cancel
        var td = $(this).parent().parent(),
        aTag = td.find('a');
        aTag.show();
        aTag.parent().parent().find('.rename-folder-form').remove();
        $('.tool-block').prop('style')['display']=''; // let :hover css rule work again

    }).on('click', '.folder-row input[name="rename_folder_save"]', function(){
        // folder rename - submit
        var td = $(this).parent().parent(),
            aTag = td.find('a'),
            newName = td.find('input[name=folder_name]').val();
        if(!newName)
            return;
        postJSON(
            aTag.attr('href'), // subfolder url
            {action:'rename_folder',name:newName},
            function(data){
                aTag.text(newName).show();
                td.find('.rename-folder-form').remove();
            }
        );

    });


    // move items button
    function handleCheckboxClick(){
        $('#new_folder_container .dropdown-toggle').prop('disabled', $('.tab-pane').find('input.checkbox:checked').length==0);
    }
    $('.tab-pane').on('click', 'input.checkbox', handleCheckboxClick);
    handleCheckboxClick();

    // draggable
    table.find('tbody tr').draggable({
        helper: "clone",
        cursorAt: { top: 10, left: 10 },
        start: function(event, ui ){
            ui.helper.addClass("link-draggable-helper").find('.tool-block').hide();
            $('body').addClass("dragging");
        },
        stop: function(event, ui ){
            $('body').removeClass("dragging");
        },
        handle: ''
    });

    $('.folder-row').droppable({
        hoverClass: "ui-selected",
        tolerance: "pointer",
        drop: function(event, ui) {
            var links = [],
                folders = []; // use an array so we can handle multiselect at some point
            if(ui.draggable.hasClass('folder-row')){
                folders.push(ui.draggable.attr('folder_id'));
            }else{
                links.push(ui.draggable.attr('link_id'));
            }
            postJSON(
                '#',
                {move_selected_items_to:$(this).attr('folder_id'),links:links,folders:folders},
                function(data){
                    ui.draggable.remove();
                }
            );
        }
    });

    function getFolderURL(folderID){
        return folderContentsURL.replace('FOLDER_ID', folderID);
    }

    function showFolderContents(folderID) {
        $.get(getFolderURL(folderID))
            .always(function (data) {
                $('.vested-table tbody').html(data.responseText || data)
            });
    }

    function renameFolder(folderID, newName){
        return postJSON(
            getFolderURL(folderID),
            {action:'rename_folder',name:newName}
        );
    }

    function moveFolder(folderID, newParentID){
        return postJSON(
            getFolderURL(newParentID),
            {action:'move_items',links:[],folders:[folderID]}
        );
    }

    function deleteFolder(folderID){
        return postJSON(
            getFolderURL(folderID),
            {action:'delete_folder'}
        );
    }

    function getFolderID(node){
        return node.li_attr['data-folder_id'];
    }

    var allowedEventsCount = 0;
    $('#folder-tree')
        .jstree({
            core: {
                check_callback: function (operation, node, node_parent, node_position, more) {
                    if(allowedEventsCount){
                        allowedEventsCount--;
                        return true;
                    }
                    var tree = this;
                    if(operation=='rename_node'){
                        newName = node_position;
                        renameFolder(getFolderID(node), newName).done(function(){
                            allowedEventsCount++;
                            tree.rename_node(node, newName);
                        });
                    }else if(operation=='move_node'){
                        moveFolder(getFolderID(node), getFolderID(node_parent)).done(function(){
                            allowedEventsCount++;
                            tree.move_node(node, node_parent);
                        });
                    }else if(operation=='delete_node'){
                        deleteFolder(getFolderID(node)).done(function(){
                            allowedEventsCount++;
                            tree.delete_node(node);
                            tree.select_node();
                        });
                    }
                    return false;
                },
                multiple: true
            },
            plugins: ['contextmenu', 'dnd', 'unique'],
            dnd: {
                check_while_dragging: false
            }
        }).on("select_node.jstree", function (e, data) {
            if(data.selected.length==1){
                showFolderContents(getFolderID(data.node));
            }
        }).on("rename_node.jstree", function (e, data) {
            renameFolder(getFolderID(data.node), data.text);
        }).on("move_node.jstree", function (e, data) {
            if(data.parent == data.old_parent)
                return;
            moveFolder(getFolderID(data.node), getFolderID(data.instance.get_node(data.parent)));
        }).on("delete_node.jstree", function (e, data) {
            deleteFolder(getFolderID(data.node));
        }).on("before.jstree", function (e, data) {
            console.log(data);
        });


});